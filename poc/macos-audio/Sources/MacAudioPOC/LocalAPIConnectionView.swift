import Observation
import SwiftUI

@available(macOS 14.0, *)
public protocol LocalAPIHealthChecking: Sendable {
    func health() async throws -> Bool
}

@available(macOS 14.0, *)
extension LocalAPIClient: LocalAPIHealthChecking {}

@available(macOS 14.0, *)
public protocol LocalBackendControlling: Sendable {
    func startBackend() async throws -> any LocalAPIHealthChecking
    func stopBackend() async throws
}

@available(macOS 14.0, *)
extension LocalBackendSupervisor: LocalBackendControlling {
    public func startBackend() async throws -> any LocalAPIHealthChecking {
        let handshake = try await Task.detached { try self.start() }.value
        return try LocalAPIClient(baseURL: handshake.baseURL, token: handshake.token)
    }

    public func stopBackend() async throws {
        try await Task.detached { try self.stop() }.value
    }
}

@available(macOS 14.0, *)
public enum LocalAPIConnectionState: Equatable {
    case notChecked
    case checking
    case starting
    case stopping
    case connected
    case unhealthy
    case failed

    fileprivate var label: String {
        switch self {
        case .notChecked: "尚未检查"
        case .checking: "正在连接本机服务…"
        case .starting: "正在启动本机服务…"
        case .stopping: "正在停止本机服务…"
        case .connected: "本机服务已连接"
        case .unhealthy: "本机服务状态异常"
        case .failed: "无法连接本机服务"
        }
    }
}

@available(macOS 14.0, *)
@MainActor
@Observable
public final class LocalAPIConnectionModel {
    private var client: (any LocalAPIHealthChecking)?
    private let backendController: (any LocalBackendControlling)?
    public private(set) var state: LocalAPIConnectionState = .notChecked

    public var canManageBackend: Bool { backendController != nil }

    public init(client: any LocalAPIHealthChecking) {
        self.client = client
        self.backendController = nil
    }

    public init(backendController: any LocalBackendControlling) {
        self.client = nil
        self.backendController = backendController
    }

    public func checkConnection() async {
        guard let client else {
            state = .failed
            return
        }
        state = .checking
        do {
            state = try await client.health() ? .connected : .unhealthy
        } catch {
            state = .failed
        }
    }

    public func startBackend() async {
        guard let backendController else {
            state = .failed
            return
        }
        state = .starting
        do {
            let startedClient = try await backendController.startBackend()
            state = .checking
            guard try await startedClient.health() else {
                try await backendController.stopBackend()
                state = .unhealthy
                return
            }
            client = startedClient
            state = .connected
        } catch {
            try? await backendController.stopBackend()
            client = nil
            state = .failed
        }
    }

    public func stopBackend() async {
        guard let backendController else { return }
        state = .stopping
        do {
            try await backendController.stopBackend()
            client = nil
            state = .notChecked
        } catch {
            state = .failed
        }
    }
}

@available(macOS 14.0, *)
public struct LocalAPIConnectionView: View {
    @State private var model: LocalAPIConnectionModel

    public init(client: any LocalAPIHealthChecking) {
        _model = State(initialValue: LocalAPIConnectionModel(client: client))
    }

    public var body: some View {
        VStack(spacing: 12) {
            Text(model.state.label)
            if model.canManageBackend {
                HStack {
                    Button("启动本机服务") {
                        Task { await model.startBackend() }
                    }
                    .disabled(model.state == .starting || model.state == .checking || model.state == .stopping || model.state == .connected)

                    Button("停止本机服务") {
                        Task { await model.stopBackend() }
                    }
                    .disabled(model.state != .connected)
                }
            }
            Button("检查本机服务") {
                Task { await model.checkConnection() }
            }
            .disabled(model.state == .checking || model.state == .starting || model.state == .stopping || model.state != .connected && model.canManageBackend)
        }
        .padding()
    }
}
