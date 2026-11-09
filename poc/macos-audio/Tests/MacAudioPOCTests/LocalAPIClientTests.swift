import Foundation
import Testing
@testable import MacAudioPOC

private final class ErrorResponseURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 503,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"detail":"secret-response-body"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class SSEErrorURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "text/event-stream"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let event = Data(
            "data: {\"error\":\"本机模型请求失败，请确认 Ollama 正在运行且模型已安装\"}\n\n".utf8
        )
        client?.urlProtocol(self, didLoad: event)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

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

@available(macOS 12.0, *)
@Test func chatStreamReportsHTTPStatusWithoutSurfacingResponseBody() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ErrorResponseURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "test-token",
        sessionConfiguration: configuration
    )

    do {
        for try await _ in client.streamChat(
            messages: [LocalChatMessage(role: "user", content: "test")]
        ) {}
        Issue.record("Expected the API client's HTTP error")
    } catch let error as LocalAPIClientError {
        #expect(error == .requestFailed(statusCode: 503))
        #expect(!error.localizedDescription.contains("secret-response-body"))
    }
}

@available(macOS 12.0, *)
@Test func chatStreamPreservesSanitizedServerSSEError() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [SSEErrorURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "test-token",
        sessionConfiguration: configuration
    )

    do {
        for try await _ in client.streamChat(
            messages: [LocalChatMessage(role: "user", content: "test")]
        ) {}
        Issue.record("Expected the SSE error event")
    } catch let error as LocalAPIStreamError {
        #expect(error.message == "本机模型请求失败，请确认 Ollama 正在运行且模型已安装")
        #expect(error.localizedDescription == error.message)
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

@Test func localUsageSnapshotDecodesUnknownProviderUsageWithoutInventingValues() throws {
    let body = """
    {"summary":{"record_count":1},"records":[{"run_id":"run-1","provider":"ollama","model":"fixture","region":"local","purpose":"chat","data_level":"L0","status":"completed","started_at":1,"completed_at":2,"latency_ms":1000,"prompt_tokens":null,"completion_tokens":null,"cost_amount":null,"cost_currency":null,"usage_state":"unknown","cost_state":"unknown"}]}
    """
    let snapshot = try JSONDecoder().decode(LocalUsageSnapshot.self, from: Data(body.utf8))

    #expect(snapshot.records.count == 1)
    #expect(snapshot.records[0].usageState == "unknown")
    #expect(snapshot.records[0].costState == "unknown")
    #expect(snapshot.records[0].promptTokens == nil)
    #expect(snapshot.records[0].costAmount == nil)
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
