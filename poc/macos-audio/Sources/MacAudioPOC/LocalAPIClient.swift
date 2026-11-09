import Foundation

public enum LocalAPIClientError: Error, Equatable {
    case invalidEndpoint
    case invalidResponse
    case requestFailed(statusCode: Int)
    case voiceStreamUnavailable(reason: String?)
    case voiceStreamRejected(String)
}

extension LocalAPIClientError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "本机服务地址无效。"
        case .invalidResponse:
            return "本机服务返回了无效响应。"
        case .requestFailed(let statusCode):
            return "本机服务请求失败（HTTP \(statusCode)）。"
        case .voiceStreamUnavailable(let reason):
            let detail = reason.map { "（\($0)）" } ?? ""
            return "无法连接本机语音服务\(detail)，请重试；音频未发送到云端。"
        case .voiceStreamRejected(let message):
            return "本机语音服务拒绝了连接：\(message)"
        }
    }
}

public struct LocalChatMessage: Codable, Equatable, Sendable {
    public let role: String
    public let content: String

    public init(role: String, content: String) {
        self.role = role
        self.content = content
    }
}

public enum LocalChatRunStatus: String, Decodable, Sendable {
    case created
    case running
    case completed
    case failed
    case cancelled

    public var displayName: String {
        switch self {
        case .created: "已创建"
        case .running: "运行中"
        case .completed: "已完成"
        case .failed: "失败"
        case .cancelled: "已取消"
        }
    }
}

public enum LocalChatStreamItem: Sendable {
    case runID(String)
    case delta(String)
}

public struct LocalImportedTextFile: Decodable, Identifiable, Sendable {
    public let importID: String
    public let displayName: String
    public let byteCount: Int
    public let characterCount: Int

    public var id: String { importID }

    enum CodingKeys: String, CodingKey {
        case importID = "import_id"
        case displayName = "display_name"
        case byteCount = "byte_count"
        case characterCount = "character_count"
    }
}

public struct LocalUsageRecord: Decodable, Identifiable, Sendable {
    public let runID: String
    public let provider: String
    public let model: String
    public let region: String
    public let purpose: String
    public let dataLevel: String
    public let status: LocalChatRunStatus
    public let startedAt: Double
    public let completedAt: Double
    public let latencyMS: Int
    public let promptTokens: Int?
    public let completionTokens: Int?
    public let costAmount: Double?
    public let costCurrency: String?
    public let usageState: String
    public let costState: String

    public var id: String { runID }

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case provider, model, region, purpose, status
        case dataLevel = "data_level"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case latencyMS = "latency_ms"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case costAmount = "cost_amount"
        case costCurrency = "cost_currency"
        case usageState = "usage_state"
        case costState = "cost_state"
    }
}

public struct LocalUsageSnapshot: Decodable, Sendable {
    public let records: [LocalUsageRecord]
}

/// Minimal native client for the authenticated, loopback-only POC health endpoint.
@available(macOS 12.0, *)
public final class LocalAPIClient: @unchecked Sendable {
    private let baseURL: URL
    private let token: String
    private let session: URLSession

    public convenience init(baseURL: URL, token: String) throws {
        try self.init(baseURL: baseURL, token: token, sessionConfiguration: nil)
    }

    init(
        baseURL: URL,
        token: String,
        sessionConfiguration: URLSessionConfiguration?
    ) throws {
        guard Self.isAllowedEndpoint(baseURL), !token.isEmpty else {
            throw LocalAPIClientError.invalidEndpoint
        }
        self.baseURL = baseURL
        self.token = token
        self.session = URLSession(
            configuration: sessionConfiguration ?? .ephemeral,
            delegate: LocalOnlyURLSessionDelegate(),
            delegateQueue: nil
        )
    }

    func makeHealthRequest() throws -> URLRequest {
        guard let url = URL(string: "/health", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    public func health() async throws -> Bool {
        let (data, response) = try await session.data(for: makeHealthRequest())
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(HealthResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.status == "ok"
    }

    public func transcribeVoice(pcm16LE: Data) async throws -> String {
        guard !pcm16LE.isEmpty, pcm16LE.count <= 960_000, pcm16LE.count.isMultiple(of: 2) else {
            throw LocalAPIClientError.invalidResponse
        }
        guard let url = URL(string: "/voice/transcribe", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = pcm16LE

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(VoiceTranscriptionResponse.self, from: data),
              !value.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.text
    }

    public func chatRunStatus(runID: String) async throws -> LocalChatRunStatus {
        guard let identifier = UUID(uuidString: runID),
              let url = URL(
                string: "/chat/runs/\(identifier.uuidString.lowercased())",
                relativeTo: baseURL
              )?.absoluteURL
        else {
            throw LocalAPIClientError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(ChatRunStatusResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.status
    }

    public func recentUsage(limit: Int = 50) async throws -> LocalUsageSnapshot {
        guard (1...100).contains(limit),
              let endpoint = URL(string: "/usage", relativeTo: baseURL),
              var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: true)
        else { throw LocalAPIClientError.invalidEndpoint }
        components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(UsageResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return LocalUsageSnapshot(records: value.records)
    }

    public func importSelectedText(data: Data, fileName: String) async throws -> LocalImportedTextFile {
        let suffix = URL(fileURLWithPath: fileName).pathExtension.lowercased()
        guard !data.isEmpty, data.count <= 10 * 1024 * 1024,
              !fileName.contains("/"), !fileName.contains("\\"),
              ["txt", "md", "markdown"].contains(suffix),
              let endpoint = URL(string: "/imports/text", relativeTo: baseURL),
              var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: true)
        else {
            throw LocalAPIClientError.invalidResponse
        }
        components.queryItems = [URLQueryItem(name: "filename", value: fileName)]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = data
        let (responseData, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 201 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let imported = try? JSONDecoder().decode(LocalImportedTextFile.self, from: responseData) else {
            throw LocalAPIClientError.invalidResponse
        }
        return imported
    }

    public func removeImportedText(importID: String) async throws {
        guard let identifier = UUID(uuidString: importID),
              let url = URL(
                string: "/imports/\(identifier.uuidString.lowercased())",
                relativeTo: baseURL
              )?.absoluteURL
        else {
            throw LocalAPIClientError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
    }

    public func openVoiceStream() throws -> LocalVoiceStream {
        guard let httpURL = URL(string: "/voice/stream", relativeTo: baseURL)?.absoluteURL,
              var components = URLComponents(url: httpURL, resolvingAgainstBaseURL: false)
        else { throw LocalAPIClientError.invalidEndpoint }
        components.scheme = httpURL.scheme == "https" ? "wss" : "ws"
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let task = session.webSocketTask(with: request)
        task.resume()
        return LocalVoiceStream(task: task)
    }

    public func streamChat(
        messages: [LocalChatMessage],
        provider: String = "ollama",
        model: String = "qwen3.5:0.8b",
        confirmedForThisRequest: Bool = false,
        importedDocumentIDs: [String] = []
    ) -> AsyncThrowingStream<LocalChatStreamItem, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = URL(string: "/chat/stream", relativeTo: baseURL)?.absoluteURL else {
                        throw LocalAPIClientError.invalidEndpoint
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.httpBody = try JSONEncoder().encode(ChatRequest(
                        messages: messages,
                        provider: provider,
                        model: model,
                        confirmedForThisRequest: confirmedForThisRequest,
                        importIDs: importedDocumentIDs
                    ))
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let httpResponse = response as? HTTPURLResponse else {
                        throw LocalAPIClientError.invalidResponse
                    }
                    guard httpResponse.statusCode == 200 else {
                        throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
                    }
                    if let runID = httpResponse.value(forHTTPHeaderField: "X-PAC-Run-ID"),
                       let identifier = UUID(uuidString: runID) {
                        continuation.yield(.runID(identifier.uuidString.lowercased()))
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let event = try JSONDecoder().decode(
                            ChatStreamEvent.self,
                            from: Data(line.dropFirst(6).utf8)
                        )
                        if let eventRunID = event.runID,
                           let identifier = UUID(uuidString: eventRunID) {
                            continuation.yield(.runID(identifier.uuidString.lowercased()))
                        }
                        if let delta = event.delta { continuation.yield(.delta(delta)) }
                        if let message = event.error { throw LocalAPIStreamError(message: message) }
                        if event.done == true { break }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func isAllowedEndpoint(_ url: URL) -> Bool {
        let portAllowed = url.port.map { (1...65535).contains($0) } ?? true
        guard url.scheme == "http",
              let host = url.host?.lowercased(),
              host == "127.0.0.1" || host == "::1",
              url.user == nil,
              url.password == nil,
              url.query == nil,
              url.fragment == nil,
              url.path.isEmpty || url.path == "/",
              portAllowed
        else {
            return false
        }
        return true
    }
}

private struct ChatRequest: Encodable {
    let messages: [LocalChatMessage]
    let provider: String
    let model: String
    let confirmedForThisRequest: Bool
    let importIDs: [String]

    enum CodingKeys: String, CodingKey {
        case messages
        case provider
        case model
        case confirmedForThisRequest = "confirmed_for_this_request"
        case importIDs = "import_ids"
    }
}

private struct ChatStreamEvent: Decodable {
    let delta: String?
    let done: Bool?
    let error: String?
    let runID: String?

    enum CodingKeys: String, CodingKey {
        case delta
        case done
        case error
        case runID = "run_id"
    }
}

private struct ChatRunStatusResponse: Decodable {
    let status: LocalChatRunStatus
}

private struct UsageResponse: Decodable {
    let records: [LocalUsageRecord]
}

public struct LocalAPIStreamError: Error, LocalizedError {
    public let message: String
    public var errorDescription: String? { message }
}

private struct HealthResponse: Decodable {
    let status: String
}

private struct VoiceTranscriptionResponse: Decodable {
    let text: String
}

private final class LocalOnlyURLSessionDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}
