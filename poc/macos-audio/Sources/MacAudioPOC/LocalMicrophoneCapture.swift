@preconcurrency import AVFoundation
import Foundation

private final class ConverterInputOnce: @unchecked Sendable {
    private let buffer: AVAudioPCMBuffer
    private var supplied = false

    init(_ buffer: AVAudioPCMBuffer) {
        self.buffer = buffer
    }

    func provide(status: UnsafeMutablePointer<AVAudioConverterInputStatus>) -> AVAudioBuffer? {
        guard !supplied else {
            status.pointee = .noDataNow
            return nil
        }
        supplied = true
        status.pointee = .haveData
        return buffer
    }
}

public enum LocalMicrophoneCaptureError: Error, LocalizedError {
    case permissionDenied
    case inputUnavailable
    case unsupportedFormat
    case converterFailed
    case captureFailed
    case emptyCapture
    case streamOverflow

    public var errorDescription: String? {
        switch self {
        case .permissionDenied:
            "麦克风权限未授予；没有开始采集。"
        case .inputUnavailable:
            "没有可用的本机麦克风输入。"
        case .unsupportedFormat:
            "本机麦克风格式无法转换为 16 kHz 单声道音频。"
        case .converterFailed:
            "本机音频格式转换失败；录音已停止。"
        case .captureFailed:
            "麦克风采集启动失败；没有保留录音。"
        case .emptyCapture:
            "没有采集到音频帧。"
        case .streamOverflow:
            "本机语音传输跟不上采集；已安全停止，没有静默丢弃音频。"
        }
    }
}

public struct CapturedVoiceFrame: Sendable {
    public let pcm16LE: Data
    public let readyAtUptime: TimeInterval

    public init(pcm16LE: Data, readyAtUptime: TimeInterval) {
        self.pcm16LE = pcm16LE
        self.readyAtUptime = readyAtUptime
    }
}

/// Captures only after `start()` is called and keeps at most 30 seconds in memory.
@available(macOS 14.0, *)
public final class LocalMicrophoneCapture: @unchecked Sendable {
    public static let sampleRateHz = 16_000
    public static let maximumDurationSeconds = 30

    private let maximumBytes = sampleRateHz * maximumDurationSeconds * MemoryLayout<Int16>.size
    private let outputFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: Double(sampleRateHz),
        channels: 1,
        interleaved: false
    )!
    private let lock = NSLock()
    private var engine: AVAudioEngine?
    private var converter: AVAudioConverter?
    private var pcm = Data()
    private var pendingFrame = Data()
    private var frameHandler: (@Sendable (CapturedVoiceFrame) -> Bool)?
    private var capturedByteCount = 0
    private var conversionFailed = false
    private var reachedLimit = false

    public init() {}

    public func start(onFrame: (@Sendable (CapturedVoiceFrame) -> Bool)? = nil) async throws {
        let permission = AVCaptureDevice.authorizationStatus(for: .audio)
        let granted: Bool
        switch permission {
        case .authorized:
            granted = true
        case .notDetermined:
            granted = await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .audio) { continuation.resume(returning: $0) }
            }
        default:
            granted = false
        }
        guard granted else { throw LocalMicrophoneCaptureError.permissionDenied }

        let audioEngine = AVAudioEngine()
        let input = audioEngine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0, inputFormat.channelCount > 0 else {
            throw LocalMicrophoneCaptureError.inputUnavailable
        }
        guard let audioConverter = AVAudioConverter(from: inputFormat, to: outputFormat) else {
            throw LocalMicrophoneCaptureError.unsupportedFormat
        }

        resetCaptureBuffer(onFrame: onFrame)

        input.installTap(onBus: 0, bufferSize: 1_024, format: inputFormat) { [weak self] buffer, _ in
            self?.append(buffer, using: audioConverter)
        }
        audioEngine.prepare()
        do {
            try audioEngine.start()
        } catch {
            input.removeTap(onBus: 0)
            throw LocalMicrophoneCaptureError.captureFailed
        }
        engine = audioEngine
        converter = audioConverter
    }

    public func finish() throws -> Data {
        stopEngine()
        lock.lock()
        let result = pcm
        pcm.removeAll(keepingCapacity: false)
        let failed = conversionFailed
        capturedByteCount = 0
        lock.unlock()
        guard !failed else { throw LocalMicrophoneCaptureError.converterFailed }
        guard !result.isEmpty else { throw LocalMicrophoneCaptureError.emptyCapture }
        return result
    }

    public func finishStreaming() throws {
        stopEngine()
        let pending: Data
        let handler: (@Sendable (CapturedVoiceFrame) -> Bool)?
        lock.lock()
        pending = pendingFrame
        pendingFrame.removeAll(keepingCapacity: false)
        handler = frameHandler
        frameHandler = nil
        let failed = conversionFailed
        capturedByteCount = 0
        lock.unlock()
        if !pending.isEmpty {
            let frame = CapturedVoiceFrame(
                pcm16LE: pending,
                readyAtUptime: ProcessInfo.processInfo.systemUptime
            )
            if handler?(frame) == false { throw LocalMicrophoneCaptureError.streamOverflow }
        }
        guard !failed else { throw LocalMicrophoneCaptureError.converterFailed }
    }

    public func discard() {
        stopEngine()
        lock.lock()
        pcm.removeAll(keepingCapacity: false)
        pendingFrame.removeAll(keepingCapacity: false)
        frameHandler = nil
        capturedByteCount = 0
        conversionFailed = false
        reachedLimit = false
        lock.unlock()
    }

    private func stopEngine() {
        guard let engine else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        self.engine = nil
        converter = nil
    }

    private func append(_ input: AVAudioPCMBuffer, using converter: AVAudioConverter) {
        let ratio = Double(Self.sampleRateHz) / input.format.sampleRate
        let capacity = AVAudioFrameCount(ceil(Double(input.frameLength) * ratio) + 64)
        guard let converted = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            markConversionFailed()
            return
        }

        var conversionError: NSError?
        let inputOnce = ConverterInputOnce(input)
        let result = converter.convert(to: converted, error: &conversionError) { _, inputStatus in
            inputOnce.provide(status: inputStatus)
        }
        guard result != .error,
              let channel = converted.int16ChannelData?.pointee,
              converted.frameLength > 0
        else {
            if result == .error { markConversionFailed() }
            return
        }
        let incoming = Data(bytes: channel, count: Int(converted.frameLength) * MemoryLayout<Int16>.size)

        var frames: [CapturedVoiceFrame] = []
        var handler: (@Sendable (CapturedVoiceFrame) -> Bool)?
        lock.lock()
        let remaining = maximumBytes - capturedByteCount
        guard remaining > 0 else {
            reachedLimit = true
            lock.unlock()
            return
        }
        let acceptedBytes = min(remaining, incoming.count) & ~1
        capturedByteCount += acceptedBytes
        if frameHandler == nil {
            pcm.append(incoming.prefix(acceptedBytes))
        } else {
            pendingFrame.append(incoming.prefix(acceptedBytes))
            while pendingFrame.count >= 6_400 {
                frames.append(CapturedVoiceFrame(
                    pcm16LE: pendingFrame.prefix(6_400),
                    readyAtUptime: ProcessInfo.processInfo.systemUptime
                ))
                pendingFrame.removeFirst(6_400)
            }
        }
        handler = frameHandler
        if acceptedBytes < incoming.count { reachedLimit = true }
        lock.unlock()
        if let handler {
            for frame in frames where !handler(frame) { markConversionFailed() }
        }
    }

    private func markConversionFailed() {
        lock.lock()
        conversionFailed = true
        lock.unlock()
    }

    private func resetCaptureBuffer(onFrame: (@Sendable (CapturedVoiceFrame) -> Bool)?) {
        lock.lock()
        pcm.removeAll(keepingCapacity: false)
        pendingFrame.removeAll(keepingCapacity: false)
        frameHandler = onFrame
        capturedByteCount = 0
        conversionFailed = false
        reachedLimit = false
        lock.unlock()
    }
}
