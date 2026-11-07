from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import wave
from array import array
from pathlib import Path

from pac_poc.asr import AudioFrame, LocalStreamingASR, SherpaOnnxRecognizer, resolve_model_files
from pac_poc.concurrent_probe import run_concurrently
from pac_poc.model_gateway import LocalModelRequest, LocalOnlyPolicy, ModelGateway, OllamaAdapter


OLLAMA_PROCESS_PATTERN = r"/Applications/Ollama.app/Contents/Resources/ollama (serve|runner)"


def process_cpu_seconds(value: str) -> float:
    text = value.strip().split("-")[-1]
    fields = text.split(":")
    total = 0.0
    for field in fields:
        total = total * 60 + float(field)
    return total


def sample_local_processes(stop: threading.Event, samples: list[dict[str, object]]) -> None:
    while not stop.is_set():
        pgrep = subprocess.run(
            ["pgrep", "-f", OLLAMA_PROCESS_PATTERN], capture_output=True, text=True
        )
        ollama_pids = [part for part in pgrep.stdout.split() if part.isdigit()]
        pids = sorted({str(os.getpid()), *ollama_pids})
        ps = subprocess.run(
            ["ps", "-o", "pid=", "-o", "rss=", "-o", "time=", "-p", ",".join(pids)],
            capture_output=True,
            text=True,
        )
        rss_bytes = 0
        cpu_by_pid: dict[str, float] = {}
        for line in ps.stdout.splitlines():
            fields = line.split()
            if len(fields) < 3:
                continue
            pid, rss_kib, cpu_time = fields[:3]
            rss_bytes += int(rss_kib) * 1024
            cpu_by_pid[pid] = process_cpu_seconds(cpu_time)
        if cpu_by_pid:
            samples.append(
                {
                    "sampled_at": time.perf_counter(),
                    "rss_bytes": rss_bytes,
                    "cpu_by_pid": cpu_by_pid,
                    "ollama_process_count": len(ollama_pids),
                }
            )
        stop.wait(1.0)


def load_asr_input(wav_path: Path, model_dir: Path) -> tuple[LocalStreamingASR, array]:
    with wave.open(str(wav_path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (
            16_000,
            1,
            2,
        ):
            raise ValueError("WAV must be mono, 16 kHz, signed PCM16")
        pcm = array("h", source.readframes(source.getnframes()))
    if not pcm or pcm.itemsize != 2:
        raise ValueError("WAV must contain non-empty PCM16 samples")
    pcm.extend([0] * (16_000 * 1600 // 1000))
    recognizer = SherpaOnnxRecognizer(**resolve_model_files(model_dir).__dict__)
    return LocalStreamingASR(recognizer, sample_rate_hz=16_000), pcm


def measure_asr(asr: LocalStreamingASR, pcm: array) -> dict[str, object]:
    frame_size = 16_000 * 200 // 1000
    latencies: list[float] = []
    event_counts = {"partial": 0, "final": 0}
    cpu_started = time.thread_time()
    for sequence, offset in enumerate(range(0, len(pcm), frame_size)):
        samples = tuple(sample / 32768.0 for sample in pcm[offset : offset + frame_size])
        started = time.perf_counter()
        event = asr.accept(AudioFrame(sequence, 16_000, samples))
        latencies.append(time.perf_counter() - started)
        if event is not None and event.kind in event_counts:
            event_counts[event.kind] += 1
    cpu_seconds = time.thread_time() - cpu_started
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.95))
    return {
        "frame_count": len(latencies),
        "frame_latency_ms": {
            "p50": ordered[len(ordered) // 2] * 1000,
            "p95": ordered[p95_index] * 1000,
            "max": max(ordered) * 1000,
        },
        "thread_cpu_seconds": cpu_seconds,
        "partial_count": event_counts["partial"],
        "final_count": event_counts["final"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure explicit local ASR and Ollama LLM work started at a barrier"
    )
    parser.add_argument("wav", type=Path, help="Explicit synthetic mono PCM16 WAV at 16 kHz")
    parser.add_argument("model_dir", type=Path, help="Explicit sherpa-onnx model directory")
    parser.add_argument("--llm-model", default="qwen3.5:0.8b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    asr_load_started = time.perf_counter()
    try:
        asr, pcm = load_asr_input(args.wav, args.model_dir)
    except (OSError, ValueError, wave.Error) as exc:
        parser.error(str(exc))
    asr_load_seconds = time.perf_counter() - asr_load_started

    gateway = ModelGateway(
        adapters={"ollama": OllamaAdapter(base_url=args.base_url)},
        policy=LocalOnlyPolicy(),
    )
    request = LocalModelRequest(
        provider="ollama",
        model=args.llm_model,
        messages=({"role": "user", "content": "Return exactly the word READY."},),
    )
    process_samples: list[dict[str, object]] = []
    stop_sampling = threading.Event()
    sampler = threading.Thread(
        target=sample_local_processes,
        args=(stop_sampling, process_samples),
        name="ollama-process-sampler",
        daemon=True,
    )
    sampler.start()

    async def call_local_model() -> dict[str, object]:
        response = await gateway.generate(request)
        return {"returned": bool(response.strip()), "response_chars": len(response)}

    try:
        result = run_concurrently(
            asr_work=lambda: measure_asr(asr, pcm),
            model_work=lambda: asyncio.run(call_local_model()),
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        return 1
    finally:
        stop_sampling.set()
        sampler.join(timeout=2)

    observed_cpu: list[float] = []
    if len(process_samples) > 1:
        first = process_samples[0]["cpu_by_pid"]
        last = process_samples[-1]["cpu_by_pid"]
        common_pids = set(first) & set(last)
        observed_cpu = [last[pid] - first[pid] for pid in common_pids]
    payload = {
        "status": "completed",
        "llm_model": args.llm_model,
        "asr_model_load_seconds": asr_load_seconds,
        "asr": result.asr.value,
        "asr_wall_seconds": result.asr.wall_seconds,
        "local_model": result.model.value,
        "local_model_wall_seconds": result.model.wall_seconds,
        "overlap_seconds": result.overlap_seconds,
        "overlap_confirmed": result.overlap_seconds > 0,
        "sampled_peak_process_rss_bytes": max(
            (int(sample["rss_bytes"]) for sample in process_samples), default=None
        ),
        "sampled_process_cpu_seconds": sum(observed_cpu) if observed_cpu else None,
        "ollama_processes_observed": max(
            (int(sample["ollama_process_count"]) for sample in process_samples), default=0
        ),
        "process_sample_count": len(process_samples),
        "gpu_usage_measured": False,
        "transcript_or_model_text_logged": False,
        "tool_execution": False,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if result.model.value["returned"] and result.asr.value["final_count"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
