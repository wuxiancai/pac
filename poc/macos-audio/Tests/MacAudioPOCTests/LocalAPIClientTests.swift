import Foundation
import Testing
@testable import MacAudioPOC

@available(macOS 12.0, *)
@Test func localAPIClientBuildsAuthenticatedLoopbackRequest() throws {
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "ephemeral-test-token"
    )

    let request = try client.makeHealthRequest()

    #expect(request.url?.absoluteString == "http://127.0.0.1:43127/health")
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer ephemeral-test-token")
    #expect(request.value(forHTTPHeaderField: "Origin") == nil)
}

@available(macOS 12.0, *)
@Test func localAPIClientRejectsNonLoopbackAndNonHTTPEndpoints() {
    #expect(throws: LocalAPIClientError.invalidEndpoint) {
        try LocalAPIClient(baseURL: URL(string: "http://example.com")!, token: "token")
    }
    #expect(throws: LocalAPIClientError.invalidEndpoint) {
        try LocalAPIClient(baseURL: URL(string: "https://127.0.0.1")!, token: "token")
    }
}

@Test func localChatRunStatusDecodesBackendLifecycleValues() throws {
    let completed = try JSONDecoder().decode(
        LocalChatRunStatus.self,
        from: Data("\"completed\"".utf8)
    )
    let cancelled = try JSONDecoder().decode(
        LocalChatRunStatus.self,
        from: Data("\"cancelled\"".utf8)
    )

    #expect(completed.displayName == "已完成")
    #expect(cancelled.displayName == "已取消")
}

@Test func voiceStreamUnavailableHasActionableLocalOnlyMessage() {
    let message = LocalAPIClientError.voiceStreamUnavailable(
        reason: "服务端测试错误"
    ).localizedDescription

    #expect(message.contains("无法连接本机语音服务"))
    #expect(message.contains("请重试"))
    #expect(message.contains("服务端测试错误"))
    #expect(message.contains("音频未发送到云端"))
}

@Test func voiceStreamRejectionPreservesServerReason() {
    let message = LocalAPIClientError.voiceStreamRejected(
        "本机语音识别正忙"
    ).localizedDescription

    #expect(message.contains("本机语音识别正忙"))
}
