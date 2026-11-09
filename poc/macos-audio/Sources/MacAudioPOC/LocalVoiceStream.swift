import Foundation

public struct VoiceRecognitionEvent: Decodable, Sendable {
    public let type: String
    public let text: String?
    public let message: String?
}

@available(macOS 12.0, *)
public final class LocalVoiceStream: @unchecked Sendable {
    private let task: URLSessionWebSocketTask
    private let decoder = JSONDecoder()
    private var nextSequence: UInt32 = 0

    init(task: URLSessionWebSocketTask) {
        self.task = task
    }

    public func start() async throws {
        try await sendJSON([
            "type": "start",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "frame_duration_ms": 200,
        ])
    }

    public func sendFrame(_ pcm: Data) async throws {
        var sequence = nextSequence.bigEndian
        var packet = Data(bytes: &sequence, count: MemoryLayout<UInt32>.size)
        packet.append(pcm)
        try await task.send(.data(packet))
        nextSequence &+= 1
    }

    public func finish() async throws {
        try await sendJSON(["type": "end"])
    }

    public func receive() async throws -> VoiceRecognitionEvent {
        let message = try await task.receive()
        let data: Data
        switch message {
        case .data(let value): data = value
        case .string(let value): data = Data(value.utf8)
        @unknown default: throw LocalAPIClientError.invalidResponse
        }
        guard let event = try? decoder.decode(VoiceRecognitionEvent.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return event
    }

    public func cancel() {
        task.cancel(with: .goingAway, reason: nil)
    }

    private func sendJSON(_ value: [String: Any]) async throws {
        let data = try JSONSerialization.data(withJSONObject: value)
        guard let text = String(data: data, encoding: .utf8) else {
            throw LocalAPIClientError.invalidResponse
        }
        try await task.send(.string(text))
    }
}
