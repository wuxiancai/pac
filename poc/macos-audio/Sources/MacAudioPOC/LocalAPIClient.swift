import Foundation

public enum LocalAPIClientError: Error, Equatable {
    case invalidEndpoint
    case invalidResponse
    case requestFailed(statusCode: Int)
}

public struct LocalChatMessage: Codable, Equatable, Sendable {
    public let role: String
    public let content: String

    public init(role: String, content: String) {
        self.role = role
        self.content = content
    }
}

/// Minimal native client for the authenticated, loopback-only POC health endpoint.
@available(macOS 12.0, *)
public final class LocalAPIClient: @unchecked Sendable {
    private let baseURL: URL
    private let token: String
    private let session: URLSession

    public init(baseURL: URL, token: String) throws {
        guard Self.isAllowedEndpoint(baseURL), !token.isEmpty else {
            throw LocalAPIClientError.invalidEndpoint
        }
        self.baseURL = baseURL
        self.token = token
        self.session = URLSession(
            configuration: .ephemeral,
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
        confirmedForThisRequest: Bool = false
    ) -> AsyncThrowingStream<String, Error> {
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
                        confirmedForThisRequest: confirmedForThisRequest
                    ))
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let httpResponse = response as? HTTPURLResponse else {
                        throw LocalAPIClientError.invalidResponse
                    }
                    guard httpResponse.statusCode == 200 else {
                        throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let event = try JSONDecoder().decode(
                            ChatStreamEvent.self,
                            from: Data(line.dropFirst(6).utf8)
                        )
                        if let delta = event.delta { continuation.yield(delta) }
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

    enum CodingKeys: String, CodingKey {
        case messages
        case provider
        case model
        case confirmedForThisRequest = "confirmed_for_this_request"
    }
}

private struct ChatStreamEvent: Decodable {
    let delta: String?
    let done: Bool?
    let error: String?
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
