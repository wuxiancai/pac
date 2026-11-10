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

private final class ImportRequestCapture: @unchecked Sendable {
    static let shared = ImportRequestCapture()
    private let lock = NSLock()
    private var storedRequest: URLRequest?
    private var storedBody: Data?

    func record(_ request: URLRequest) {
        var body = request.httpBody
        if body == nil, let stream = request.httpBodyStream {
            stream.open()
            var bytes: [UInt8] = []
            var buffer = [UInt8](repeating: 0, count: 8_192)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                bytes.append(contentsOf: buffer.prefix(count))
            }
            stream.close()
            body = Data(bytes)
        }
        lock.lock()
        storedRequest = request
        storedBody = body
        lock.unlock()
    }

    func take() -> (URLRequest, Data?)? {
        lock.lock()
        defer { lock.unlock() }
        let request = storedRequest
        let body = storedBody
        storedRequest = nil
        storedBody = nil
        guard let request else { return nil }
        return (request, body)
    }
}

private final class ImportResponseURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        ImportRequestCapture.shared.record(request)
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 201,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let body = #"{"import_id":"11111111-1111-4111-8111-111111111111","display_name":"notes.md","byte_count":12,"character_count":12}"#
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class BackupExportCapture: @unchecked Sendable {
    static let shared = BackupExportCapture()
    private let lock = NSLock()
    private var stored: [String: (URLRequest, Data?)] = [:]
    func record(_ request: URLRequest) {
        var body = request.httpBody
        if body == nil, let stream = request.httpBodyStream {
            stream.open()
            var bytes = [UInt8](repeating: 0, count: 4096)
            var collected: [UInt8] = []
            while stream.hasBytesAvailable {
                let count = stream.read(&bytes, maxLength: bytes.count)
                if count <= 0 { break }
                collected.append(contentsOf: bytes.prefix(count))
            }
            stream.close()
            body = Data(collected)
        }
        lock.lock(); stored[request.url?.path ?? ""] = (request, body); lock.unlock()
    }
    func take(path: String) -> (URLRequest, Data?)? {
        lock.lock()
        defer { lock.unlock() }
        return stored.removeValue(forKey: path)
    }
}

private final class BackupExportURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        BackupExportCapture.shared.record(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: 201, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"created":true,"bytes_written":256}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class BackupRestoreURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        BackupExportCapture.shared.record(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"restored":true,"prebackup_path":"/private/pre-restore.sqlcipher"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class ImportNetworkProbe: @unchecked Sendable {
    static let shared = ImportNetworkProbe()
    private let lock = NSLock()
    private var requestCount = 0

    func reset() {
        lock.lock()
        requestCount = 0
        lock.unlock()
    }

    func recordRequest() {
        lock.lock()
        requestCount += 1
        lock.unlock()
    }

    var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return requestCount
    }
}

private final class ImportRejectProbeURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        ImportNetworkProbe.shared.recordRequest()
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 503,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class ConversationAPIURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let body: String
        if request.httpMethod == "POST" {
            body = #"{"id":"22222222-2222-4222-8222-222222222222","title":"New","created_at":"2026-11-10T00:00:00+00:00","updated_at":"2026-11-10T00:00:00+00:00","message_count":0}"#
        } else if request.httpMethod == "PATCH" {
            body = #"{"id":"11111111-1111-4111-8111-111111111111","title":"Renamed","created_at":"2026-11-09T00:00:00+00:00","updated_at":"2026-11-10T00:00:00+00:00","message_count":2}"#
        } else {
            body = #"{"conversations":[{"id":"11111111-1111-4111-8111-111111111111","title":"Existing","created_at":"2026-11-09T00:00:00+00:00","updated_at":"2026-11-09T00:00:00+00:00","message_count":2}]}"#
        }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: request.httpMethod == "POST" ? 201 : 200,
            httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class ChatHistoryURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let body = #"{"conversation_id":"11111111-1111-4111-8111-111111111111","messages":[{"id":"33333333-3333-4333-8333-333333333333","role":"user","content":"persisted prompt"}]}"#
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

private final class PaginatedChatHistoryURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        BackupExportCapture.shared.record(request)
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let body = #"{"conversation_id":"11111111-1111-4111-8111-111111111111","messages":[{"id":"33333333-3333-4333-8333-333333333333","role":"user","content":"older page"}],"has_more":true}"#
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class ChatRequestCapture: @unchecked Sendable {
    static let shared = ChatRequestCapture()
    private let lock = NSLock()
    private var storedRequest: URLRequest?
    private var storedBody: Data?

    func record(_ request: URLRequest) {
        var body = request.httpBody
        if body == nil, let stream = request.httpBodyStream {
            stream.open()
            var bytes: [UInt8] = []
            var buffer = [UInt8](repeating: 0, count: 8_192)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                bytes.append(contentsOf: buffer.prefix(count))
            }
            stream.close()
            body = Data(bytes)
        }
        lock.lock()
        storedRequest = request
        storedBody = body
        lock.unlock()
    }

    func take() -> (URLRequest, Data?)? {
        lock.lock()
        defer { lock.unlock() }
        let request = storedRequest
        let body = storedBody
        storedRequest = nil
        storedBody = nil
        guard let request else { return nil }
        return (request, body)
    }
}

private final class ChatRequestCaptureURLProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        ChatRequestCapture.shared.record(request)
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "text/event-stream"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("data: {\"done\":true}\n\n".utf8))
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

@available(macOS 12.0, *)
@Test func chatStreamIncludesImportedDocumentIDsInAuthenticatedRequest() async throws {
    _ = ChatRequestCapture.shared.take()
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ChatRequestCaptureURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "test-token",
        sessionConfiguration: configuration
    )

    for try await _ in client.streamChat(
        messages: [LocalChatMessage(id: "33333333-3333-4333-8333-333333333333", role: "user", content: "Summarize the attached notes")],
        importedDocumentIDs: ["11111111-1111-4111-8111-111111111111"],
        conversationID: "22222222-2222-4222-8222-222222222222"
    ) {}

    let captured = try #require(ChatRequestCapture.shared.take())
    #expect(captured.0.url?.path == "/chat/stream")
    #expect(captured.0.value(forHTTPHeaderField: "Authorization") == "Bearer test-token")
    let body = try #require(captured.1)
    let object = try JSONSerialization.jsonObject(with: body)
    let payload = try #require(object as? [String: Any])
    #expect(payload["import_ids"] as? [String] == ["11111111-1111-4111-8111-111111111111"])
    #expect(payload["conversation_id"] as? String == "22222222-2222-4222-8222-222222222222")
    #expect(payload["messages"] != nil)
    let messages = try #require(payload["messages"] as? [[String: Any]])
    #expect(messages[0]["id"] == nil)
}


@available(macOS 12.0, *)
@Test func conversationClientListsAndCreatesPersistedConversations() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ConversationAPIURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "conversation-token",
        sessionConfiguration: configuration
    )

    let existing = try await client.conversations()
    let created = try await client.createConversation(title: "New")
    let renamed = try await client.renameConversation(
        id: "11111111-1111-4111-8111-111111111111", title: "Renamed"
    )
    #expect(existing.count == 1)
    #expect(existing[0].title == "Existing")
    #expect(existing[0].messageCount == 2)
    #expect(created.title == "New")
    #expect(created.messageCount == 0)
    #expect(renamed.title == "Renamed")
}

@available(macOS 12.0, *)
@Test func chatHistoryLoadsFromAuthenticatedLocalEndpoint() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ChatHistoryURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "history-token",
        sessionConfiguration: configuration
    )

    let history = try await client.chatHistory()
    #expect(history.conversationID == "11111111-1111-4111-8111-111111111111")
    #expect(history.messages == [LocalChatMessage(
        id: "33333333-3333-4333-8333-333333333333", role: "user", content: "persisted prompt"
    )])
    #expect(history.messages[0].id == "33333333-3333-4333-8333-333333333333")
    try await client.deleteChatHistory(conversationID: "11111111-1111-4111-8111-111111111111")
}

@Test func chatHistoryPaginationUsesStableMessageCursorAndBoundedLimit() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [PaginatedChatHistoryURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!, token: "history-token",
        sessionConfiguration: configuration
    )
    let history = try await client.chatHistory(
        conversationID: "11111111-1111-4111-8111-111111111111",
        beforeMessageID: "22222222-2222-4222-8222-222222222222", limit: 75
    )
    #expect(history.hasMore)
    #expect(history.messages[0].content == "older page")
    let captured = try #require(BackupExportCapture.shared.take(path: "/chat/history"))
    let request = captured.0
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer history-token")
    let query = URLComponents(url: try #require(request.url), resolvingAgainstBaseURL: false)?.queryItems
    #expect(query?.first(where: { $0.name == "before_message_id" })?.value == "22222222-2222-4222-8222-222222222222")
    #expect(query?.first(where: { $0.name == "limit" })?.value == "75")
    await #expect(throws: LocalAPIClientError.invalidEndpoint) {
        _ = try await client.chatHistory(limit: 201)
    }
}

@Test func memoryVersionSnapshotDecodesPersistedCorrection() throws {
    let data = Data(#"{"id":"11111111-1111-4111-8111-111111111111","version_no":2,"snapshot":{"subject":"Project Atlas","content":"Keep it local","category":"decision","confirmed_at":"2026-11-10T02:00:00+00:00","source_message_id":null},"change_reason":"user_confirmed_edit","created_at":"2026-11-10T02:00:00+00:00"}"#.utf8)
    let version = try JSONDecoder().decode(LocalMemoryVersion.self, from: data)
    #expect(version.versionNo == 2)
    #expect(version.snapshot.content == "Keep it local")
    #expect(version.changeReason == "user_confirmed_edit")
}

@Test func memorySourceDecodesConversationContext() throws {
    let data = Data(#"{"message_id":"33333333-3333-4333-8333-333333333333","conversation_id":"11111111-1111-4111-8111-111111111111","conversation_title":"Project discussion","role":"user","content":"Keep the archive local","created_at":"2026-11-10T02:00:00+00:00"}"#.utf8)
    let source = try JSONDecoder().decode(LocalMemorySource.self, from: data)
    #expect(source.conversationTitle == "Project discussion")
    #expect(source.content == "Keep the archive local")
}

@available(macOS 12.0, *)
@Test func selectedTextImportUsesAuthenticatedLoopbackAndSendsNoPath() async throws {
    _ = ImportRequestCapture.shared.take()
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ImportResponseURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "test-token",
        sessionConfiguration: configuration
    )
    let contents = Data("hello world\n".utf8)

    let imported = try await client.importSelectedText(data: contents, fileName: "notes.md")
    let captured = try #require(ImportRequestCapture.shared.take())
    let request = captured.0
    let sentBody = try #require(captured.1)

    #expect(imported.displayName == "notes.md")
    #expect(imported.byteCount == contents.count)
    #expect(imported.characterCount == contents.count)
    #expect(request.httpMethod == "POST")
    #expect(request.url?.absoluteString == "http://127.0.0.1:43127/imports/text?filename=notes.md")
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer test-token")
    #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/octet-stream")
    #expect(sentBody == contents)
    #expect(!request.url!.absoluteString.contains("/Users/"))
}

@available(macOS 12.0, *)
@Test func selectedTextImportRejectsPDFAndOversizedFilesBeforeNetwork() async throws {
    ImportNetworkProbe.shared.reset()
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ImportRejectProbeURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!,
        token: "test-token",
        sessionConfiguration: configuration
    )

    do {
        _ = try await client.importSelectedText(data: Data("%PDF".utf8), fileName: "notes.pdf")
        Issue.record("Expected PDF import to be rejected")
    } catch let error as LocalAPIClientError {
        #expect(error == .invalidResponse)
    }
    do {
        _ = try await client.importSelectedText(
            data: Data(repeating: 0, count: 10 * 1024 * 1024 + 1),
            fileName: "oversized.txt"
        )
        Issue.record("Expected oversized import to be rejected")
    } catch let error as LocalAPIClientError {
        #expect(error == .invalidResponse)
    }
    #expect(ImportNetworkProbe.shared.count == 0)
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

@Test func encryptedBackupExportSendsAuthenticatedOneTimePasswordRequest() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [BackupExportURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!, token: "local-token",
        sessionConfiguration: configuration
    )
    let count = try await client.exportEncryptedBackup(
        destinationPath: "/tmp/fixture.pacbackup", password: "one-time-secret"
    )
    #expect(count == 256)
    let captured = try #require(BackupExportCapture.shared.take(path: "/backups/export"))
    let request = captured.0
    #expect(request.httpMethod == "POST")
    #expect(request.url?.path == "/backups/export")
    #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer local-token")
    let body = try #require(captured.1)
    let payload = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
    #expect(payload["destination_path"] as? String == "/tmp/fixture.pacbackup")
    #expect(payload["password"] as? String == "one-time-secret")
    #expect(payload["replace_existing"] as? Bool == false)
}

@Test func encryptedBackupRestoreSendsAuthenticatedPathAndDecodesPrebackupLocation() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [BackupRestoreURLProtocol.self]
    let client = try LocalAPIClient(
        baseURL: URL(string: "http://127.0.0.1:43127")!, token: "local-token",
        sessionConfiguration: configuration
    )
    let prebackupPath = try await client.restoreEncryptedBackup(
        sourcePath: "/tmp/fixture.pacbackup", password: "one-time-secret"
    )
    #expect(prebackupPath == "/private/pre-restore.sqlcipher")
    let captured = try #require(BackupExportCapture.shared.take(path: "/backups/restore"))
    #expect(captured.0.httpMethod == "POST")
    #expect(captured.0.url?.path == "/backups/restore")
    #expect(captured.0.value(forHTTPHeaderField: "Authorization") == "Bearer local-token")
    let body = try #require(captured.1)
    let payload = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
    #expect(payload["source_path"] as? String == "/tmp/fixture.pacbackup")
    #expect(payload["password"] as? String == "one-time-secret")
}

@Test func localUsageSnapshotDecodesUnknownProviderUsageWithoutInventingValues() throws {
    let body = """
    {"summary":{"record_count":1},"records":[{"run_id":"run-1","provider":"ollama","model":"fixture","region":"","purpose":"chat","data_level":"L0","status":"completed","started_at":1,"completed_at":2,"latency_ms":1000,"prompt_tokens":null,"completion_tokens":null,"cached_prompt_tokens":null,"cost_amount":null,"cost_currency":null,"usage_state":"unknown","cost_state":"unknown"}]}
    """
    let snapshot = try JSONDecoder().decode(LocalUsageSnapshot.self, from: Data(body.utf8))

    #expect(snapshot.records.count == 1)
    #expect(snapshot.records[0].usageState == "unknown")
    #expect(snapshot.records[0].costState == "unknown")
    #expect(snapshot.records[0].promptTokens == nil)
    #expect(snapshot.records[0].cachedPromptTokens == nil)
    #expect(snapshot.records[0].costAmount == nil)
    #expect(snapshot.records[0].startedAtDate.timeIntervalSince1970 == 1)
    #expect(snapshot.records[0].regionDisplayName == "本机")
    #expect(snapshot.records[0].purposeDisplayName == "聊天")
    #expect(snapshot.records[0].dataLevelDisplayName == "数据等级 L0")

    let cloudBody = body
        .replacingOccurrences(of: "\"provider\":\"ollama\"", with: "\"provider\":\"deepseek\"")
        .replacingOccurrences(of: "\"region\":\"\"", with: "\"region\":\"china\"")
        .replacingOccurrences(of: "\"purpose\":\"chat\"", with: "\"purpose\":\"beta-interactive-chat\"")
        .replacingOccurrences(of: "\"data_level\":\"L0\"", with: "\"data_level\":\"L2\"")
    let cloudSnapshot = try JSONDecoder().decode(
        LocalUsageSnapshot.self,
        from: Data(cloudBody.utf8)
    )
    #expect(cloudSnapshot.records[0].purposeDisplayName == "交互式聊天")
    #expect(cloudSnapshot.records[0].dataLevelDisplayName == "数据等级 L2")
    #expect(cloudSnapshot.records[0].regionDisplayName == "china")
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
