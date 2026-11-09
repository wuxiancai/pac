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

@Test func voiceStreamUnavailableHasActionableLocalOnlyMessage() {
    let message = LocalAPIClientError.voiceStreamUnavailable.localizedDescription

    #expect(message.contains("稍后重试"))
    #expect(message.contains("音频未发送到云端"))
}
