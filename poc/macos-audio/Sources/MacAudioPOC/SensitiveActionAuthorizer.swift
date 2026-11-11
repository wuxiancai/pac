import LocalAuthentication

@MainActor
protocol DeviceAuthenticationEvaluating: AnyObject {
    func canEvaluate(policy: LAPolicy) -> Bool
    func evaluate(policy: LAPolicy, reason: String) async throws
    func invalidate()
}

@MainActor
private final class LAContextAuthenticationEvaluator: DeviceAuthenticationEvaluating {
    private let context: LAContext

    init(context: LAContext) {
        self.context = context
    }

    func canEvaluate(policy: LAPolicy) -> Bool {
        var error: NSError?
        return context.canEvaluatePolicy(policy, error: &error)
    }

    func evaluate(policy: LAPolicy, reason: String) async throws {
        let authenticated = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Bool, Error>) in
            context.evaluatePolicy(policy, localizedReason: reason) { authenticated, error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume(returning: authenticated) }
            }
        }
        guard authenticated else {
            throw SensitiveActionAuthorizationError.authenticationUnavailable
        }
    }

    func invalidate() {
        context.invalidate()
    }
}

@MainActor
public protocol SensitiveActionAuthorizing: AnyObject {
    func authorize(reason: String) async throws
}

@MainActor
public protocol CancellableSensitiveActionAuthorizing: SensitiveActionAuthorizing {
    func cancel()
}

public enum SensitiveActionAuthorizationError: Error {
    case authenticationUnavailable
    /// Kept for source compatibility with the earlier biometric-only POC.
    case touchIDUnavailable
}

public enum DeviceAuthenticationFailureMessage {
    public static func localized(for error: Error) -> String? {
        guard let error = error as? LAError else { return nil }
        return switch error.code {
        case .appCancel, .userCancel:
            "本机认证已取消，未开始恢复。"
        case .systemCancel:
            "系统中断本机认证，未开始恢复。"
        default:
            nil
        }
    }
}

@MainActor
public final class TouchIDAuthorizer: CancellableSensitiveActionAuthorizing {
    static let authenticationPolicy: LAPolicy = .deviceOwnerAuthentication

    private let evaluator: any DeviceAuthenticationEvaluating

    public init(context: LAContext = LAContext()) {
        self.evaluator = LAContextAuthenticationEvaluator(context: context)
    }

    init(evaluator: any DeviceAuthenticationEvaluating) {
        self.evaluator = evaluator
    }

    public func authorize(reason: String) async throws {
        guard evaluator.canEvaluate(policy: Self.authenticationPolicy) else {
            throw SensitiveActionAuthorizationError.authenticationUnavailable
        }
        try await evaluator.evaluate(policy: Self.authenticationPolicy, reason: reason)
    }

    public func cancel() {
        evaluator.invalidate()
    }
}

@MainActor
public final class CredentialManagementService {
    private let store: KeychainCredentialStore
    private let authorizer: any SensitiveActionAuthorizing

    public init(
        service: String,
        authorizer: any SensitiveActionAuthorizing
    ) {
        self.store = KeychainCredentialStore(service: service)
        self.authorizer = authorizer
    }

    public func save(_ secret: String, account: String) async throws {
        try await authorizer.authorize(reason: "保存模型服务凭据")
        try store.save(secret, account: account)
    }

    public func delete(account: String) async throws {
        try await authorizer.authorize(reason: "删除模型服务凭据")
        try store.delete(account: account)
    }

    public func contains(account: String) throws -> Bool {
        try store.contains(account: account)
    }
}
