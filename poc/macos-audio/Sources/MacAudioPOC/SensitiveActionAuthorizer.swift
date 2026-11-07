import LocalAuthentication

@MainActor
public protocol SensitiveActionAuthorizing: AnyObject {
    func authorize(reason: String) async throws
}

public enum SensitiveActionAuthorizationError: Error {
    case authenticationUnavailable
    /// Kept for source compatibility with the earlier biometric-only POC.
    case touchIDUnavailable
}

@MainActor
public final class TouchIDAuthorizer: SensitiveActionAuthorizing {
    static let authenticationPolicy: LAPolicy = .deviceOwnerAuthentication

    private let context: LAContext

    public init(context: LAContext = LAContext()) {
        self.context = context
    }

    public func authorize(reason: String) async throws {
        var error: NSError?
        guard context.canEvaluatePolicy(Self.authenticationPolicy, error: &error)
        else {
            throw SensitiveActionAuthorizationError.authenticationUnavailable
        }
        try await context.evaluatePolicy(
            Self.authenticationPolicy,
            localizedReason: reason
        )
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
