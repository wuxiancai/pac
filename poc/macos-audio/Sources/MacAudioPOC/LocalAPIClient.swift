import Foundation

public enum LocalAPIClientError: Error, Equatable {
    case invalidEndpoint
    case invalidResponse
    case requestFailed(statusCode: Int)
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

private struct HealthResponse: Decodable {
    let status: String
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
