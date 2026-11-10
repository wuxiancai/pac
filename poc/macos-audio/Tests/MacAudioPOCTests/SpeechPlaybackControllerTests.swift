import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeSpeechEngine: SpeechEngine {
    private(set) var spokenTexts: [String] = []
    private(set) var spokenRates: [Float] = []
    private(set) var stopCount = 0
    var isSpeaking = false
    var stopResult = true

    func speak(_ text: String, rate: Float) {
        spokenTexts.append(text)
        spokenRates.append(rate)
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

    #expect(controller.speak("测试语音打断") == .started)
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

    #expect(controller.speak(" \n ") == .emptyText)
    #expect(controller.state == .idle)
    #expect(engine.spokenTexts.isEmpty)
}

@MainActor
@Test func newSpeechStopsCurrentUtteranceInsteadOfQueuingBehindIt() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(controller.speak("第一条回复") == .started)
    #expect(controller.speak("第二条回复") == .started)

    #expect(engine.stopCount == 1)
    #expect(engine.spokenTexts == ["第一条回复", "第二条回复"])
    #expect(controller.state == .speaking)
}

@MainActor
@Test func emptySpeechDoesNotInterruptCurrentUtterance() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(controller.speak("正在朗读") == .started)
    #expect(controller.speak(" \n ") == .emptyText)

    #expect(engine.stopCount == 0)
    #expect(engine.spokenTexts == ["正在朗读"])
}

@MainActor
@Test func failedInterruptDoesNotQueueNewSpeech() {
    let engine = FakeSpeechEngine()
    engine.stopResult = false
    let controller = SpeechPlaybackController(engine: engine)

    #expect(controller.speak("第一条回复") == .started)
    #expect(controller.speak("第二条回复") == .existingSpeechCouldNotBeStopped)

    #expect(engine.spokenTexts == ["第一条回复"])
    #expect(controller.state == .speaking)
}

@MainActor
@Test func interruptWhenIdleDoesNotCallEngine() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(!controller.interrupt())
    #expect(engine.stopCount == 0)
}

@MainActor
@Test func speechPlaybackUsesSelectedRatePreset() {
    let engine = FakeSpeechEngine()
    let controller = SpeechPlaybackController(engine: engine)

    #expect(controller.speak("语速检查", rate: SpeechRatePreset.fast.rate) == .started)
    #expect(engine.spokenRates == [SpeechRatePreset.fast.rate])
}
