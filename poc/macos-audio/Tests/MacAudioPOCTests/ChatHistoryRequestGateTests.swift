import Testing
@testable import MacAudioPOC

@Test func invalidatingHistoryRequestsRejectsAnOlderPage() {
    var gate = ChatHistoryRequestGate()
    let request = gate.beginPage(conversationID: "conversation-a")!

    gate.invalidate()

    #expect(!gate.canApplyPage(
        request,
        currentConversationID: "conversation-b",
        responseConversationID: "conversation-a"
    ))
    #expect(!gate.isLoadingOlderMessages)
}

@Test func finishingAnOlderPageDoesNotClearANewerPageLoadingState() {
    var gate = ChatHistoryRequestGate()
    let olderRequest = gate.beginPage(conversationID: "conversation-a")!

    gate.invalidate()
    let currentRequest = gate.beginPage(conversationID: "conversation-b")!
    #expect(gate.isLoadingOlderMessages)

    let finishedOlderPage = gate.finishPage(olderRequest)
    #expect(!finishedOlderPage)
    #expect(gate.isLoadingOlderMessages)
    let finishedCurrentPage = gate.finishPage(currentRequest)
    #expect(finishedCurrentPage)
    #expect(!gate.isLoadingOlderMessages)
}
