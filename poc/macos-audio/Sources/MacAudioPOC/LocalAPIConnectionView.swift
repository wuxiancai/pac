import Observation
import SwiftUI

@available(macOS 14.0, *)
public protocol LocalAPIHealthChecking: Sendable {
    func health() async throws -> Bool
}

@available(macOS 14.0, *)
extension LocalAPIClient: LocalAPIHealthChecking {}

@available(macOS 14.0, *)
public enum LocalAPIConnectionState: Equatable {
    case notChecked
    case checking
    case connected
    case unhealthy
    case failed

    fileprivate var label: String {
        switch self {
        case .notChecked: "尚未检查"
        case .checking: "正在连接本机服务…"
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
    private let client: any LocalAPIHealthChecking
    public private(set) var state: LocalAPIConnectionState = .notChecked

    public init(client: any LocalAPIHealthChecking) {
        self.client = client
    }

    public func checkConnection() async {
        state = .checking
        do {
            state = try await client.health() ? .connected : .unhealthy
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
            Button("检查本机服务") {
                Task { await model.checkConnection() }
            }
            .disabled(model.state == .checking)
        }
        .padding()
    }
}
