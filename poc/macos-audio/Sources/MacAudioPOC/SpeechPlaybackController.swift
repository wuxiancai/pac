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

@MainActor
public protocol SpeechEngine: AnyObject {
    var isSpeaking: Bool { get }
    func speak(_ text: String)
    func stopImmediately() -> Bool
}

@MainActor
@available(macOS 10.14, *)
public final class AVSpeechEngine: SpeechEngine {
    private let synthesizer = AVSpeechSynthesizer()

    public init() {}

    public var isSpeaking: Bool { synthesizer.isSpeaking }

    public func speak(_ text: String) {
        synthesizer.speak(AVSpeechUtterance(string: text))
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
    public func speak(_ text: String) -> SpeechPlaybackStartResult {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .emptyText
        }
        if engine.isSpeaking, !engine.stopImmediately() {
            return .existingSpeechCouldNotBeStopped
        }
        engine.speak(text)
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
