import AVFoundation

public enum SpeechPlaybackState: Equatable {
    case idle
    case speaking
    case interrupted
}

public enum SpeechPlaybackStartResult: Equatable {
    case started
    case emptyText
    case existingSpeechCouldNotBeStopped
}

public enum SpeechRatePreset: String, CaseIterable, Identifiable {
    case slow
    case normal
    case fast

    public var id: String { rawValue }
    public var title: String {
        switch self {
        case .slow: "较慢"
        case .normal: "标准"
        case .fast: "较快"
        }
    }
    public var rate: Float {
        switch self {
        case .slow: 0.42
        case .normal: 0.5
        case .fast: 0.58
        }
    }
}

@MainActor
public protocol SpeechEngine: AnyObject {
    var isSpeaking: Bool { get }
    func speak(_ text: String, rate: Float)
    func stopImmediately() -> Bool
}

@MainActor
@available(macOS 10.14, *)
public final class AVSpeechEngine: SpeechEngine {
    private let synthesizer = AVSpeechSynthesizer()

    public init() {}

    public var isSpeaking: Bool { synthesizer.isSpeaking }

    public func speak(_ text: String, rate: Float) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = rate
        synthesizer.speak(utterance)
    }

    public func stopImmediately() -> Bool {
        synthesizer.stopSpeaking(at: .immediate)
    }
}

@MainActor
public final class SpeechPlaybackController {
    private let engine: any SpeechEngine
    public private(set) var state: SpeechPlaybackState = .idle

    public init(engine: any SpeechEngine) {
        self.engine = engine
    }

    @discardableResult
    public func speak(
        _ text: String,
        rate: Float = 0.5
    ) -> SpeechPlaybackStartResult {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .emptyText
        }
        if engine.isSpeaking, !engine.stopImmediately() {
            return .existingSpeechCouldNotBeStopped
        }
        engine.speak(text, rate: rate)
        state = .speaking
        return .started
    }

    @discardableResult
    public func interrupt() -> Bool {
        guard state == .speaking, engine.isSpeaking else { return false }
        guard engine.stopImmediately() else { return false }
        state = .interrupted
        return true
    }
}
