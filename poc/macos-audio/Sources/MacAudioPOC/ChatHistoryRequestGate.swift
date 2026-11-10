import Foundation

public struct ChatHistoryRequestGate: Sendable {
    public struct PageRequest: Equatable, Sendable {
        public let generation: UInt64
        fileprivate let id: UUID
        fileprivate let conversationID: String
    }

    public private(set) var generation: UInt64 = 0
    private var activePageRequestID: UUID?

    public var isLoadingOlderMessages: Bool { activePageRequestID != nil }

    public init() {}

    public mutating func invalidate() {
        generation &+= 1
        activePageRequestID = nil
    }

    public func isCurrent(_ requestGeneration: UInt64) -> Bool {
        requestGeneration == generation
    }

    public mutating func beginPage(conversationID: String) -> PageRequest? {
        guard activePageRequestID == nil else { return nil }
        let id = UUID()
        activePageRequestID = id
        return PageRequest(
            generation: generation,
            id: id,
            conversationID: conversationID
        )
    }

    public func canApplyPage(
        _ request: PageRequest,
        currentConversationID: String?,
        responseConversationID: String?
    ) -> Bool {
        request.generation == generation
            && currentConversationID == request.conversationID
            && responseConversationID == request.conversationID
    }

    @discardableResult
    public mutating func finishPage(_ request: PageRequest) -> Bool {
        guard activePageRequestID == request.id else { return false }
        activePageRequestID = nil
        return true
    }
}
