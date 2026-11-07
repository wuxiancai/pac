import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeSpeechEngine: SpeechEngine {
    private(set) var spokenTexts: [String] = []
    private(set) var stopCount = 0
    var isSpeaking = false
    var stopResult = true

    func speak(_ text: String) {
        spokenTexts.append(text)
        isSpeaking = true
    }

    func stopImmediately() -> Bool {
        stopCount += 1
        isSpeaking = false
        return stopResult
    }
}

@MainActor
@Test func interruptStopsCurrentSpeechImmediately() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(controller.speak("测试语音打断"))
    #expect(controller.state == .speaking)
    #expect(controller.interrupt())
    #expect(controller.state == .interrupted)
    #expect(engine.stopCount == 1)
    #expect(!engine.isSpeaking)
}

@MainActor
@Test func emptyTextDoesNotStartSpeech() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(!controller.speak(" \n "))
    #expect(controller.state == .idle)
    #expect(engine.spokenTexts.isEmpty)
}

@MainActor
@Test func interruptWhenIdleDoesNotCallEngine() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(!controller.interrupt())
    #expect(engine.stopCount == 0)
}
