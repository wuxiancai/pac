from __future__ import annotations

import argparse
import asyncio
import json

from pac_poc.model_gateway import LocalModelRequest, LocalOnlyPolicy, ModelGateway, OllamaAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe one local Ollama model's tool-call response; never execute tools"
    )
    parser.add_argument("--model", default="qwen3.5:0.8b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    request = LocalModelRequest(
        provider="ollama",
        model=args.model,
        messages=(
            {
                "role": "user",
                "content": "Call lookup exactly once with key phase0-probe. Do not answer in prose.",
            },
        ),
        tools=(
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Synthetic capability probe. This function is not executed.",
                    "parameters": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                        "required": ["key"],
                        "additionalProperties": False,
                    },
                },
            },
        ),
    )
    gateway = ModelGateway(
        adapters={"ollama": OllamaAdapter(base_url=args.base_url)},
        policy=LocalOnlyPolicy(),
    )
    try:
        result = asyncio.run(gateway.call_with_tools(request))
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        return 1

    print(
        json.dumps(
            {
                "status": "tool_call_returned" if result.tool_calls else "no_tool_call",
                "model": args.model,
                "text": result.text,
                "tool_calls": [
                    {"name": call.name, "arguments": dict(call.arguments)}
                    for call in result.tool_calls
                ],
                "executed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result.tool_calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
