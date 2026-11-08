import Observation
import SwiftUI

@available(macOS 14.0, *)
public enum SystemAuthenticationTestState: Equatable {
    case ready
    case evaluating
    case authenticated
    case notAuthenticated

    fileprivate var label: String {
        switch self {
        case .ready: "尚未测试系统认证"
        case .evaluating: "正在等待系统认证…"
        case .authenticated: "系统认证成功；未访问钥匙串"
        case .notAuthenticated: "认证未完成或被系统拒绝"
        }
    }
}

@available(macOS 14.0, *)
@MainActor
@Observable
public final class SystemAuthenticationTestModel {
    private let authorizer: any SensitiveActionAuthorizing
    public private(set) var state: SystemAuthenticationTestState = .ready

    public init(authorizer: any SensitiveActionAuthorizing) {
        self.authorizer = authorizer
    }

    public func testAuthentication() async {
        guard state != .evaluating else { return }
        state = .evaluating
        do {
            try await authorizer.authorize(
                reason: "验证本机系统认证能力；本测试不会修改钥匙串。"
            )
            state = .authenticated
        } catch {
            state = .notAuthenticated
        }
    }
}

@available(macOS 14.0, *)
public struct SystemAuthenticationTestView: View {
    @State private var model: SystemAuthenticationTestModel

    public init(authorizer: any SensitiveActionAuthorizing = TouchIDAuthorizer()) {
        _model = State(initialValue: SystemAuthenticationTestModel(authorizer: authorizer))
    }

    public var body: some View {
        VStack(spacing: 8) {
            Text("此测试只触发 macOS 本机身份验证，不读写或删除钥匙串。系统会选择可用的认证方式。")
                .multilineTextAlignment(.center)
            Button("测试 macOS 系统认证提示") {
                Task { await model.testAuthentication() }
            }
            .disabled(model.state == .evaluating)
            Text(model.state.label)
                .accessibilityIdentifier("system-authentication-status")
        }
        .padding()
    }
}
