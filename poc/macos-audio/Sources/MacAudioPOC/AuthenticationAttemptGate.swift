import Foundation

/// Prevents a cancelled or superseded authentication callback from authorizing
/// a sensitive operation after a later UI action has taken over.
@MainActor
public final class AuthenticationAttemptGate {
    private var activeAttempt: UUID?

    public init() {}

    @discardableResult
    public func begin() -> UUID {
        let attempt = UUID()
        activeAttempt = attempt
        return attempt
    }

    public func claim(_ attempt: UUID) -> Bool {
        guard activeAttempt == attempt else { return false }
        activeAttempt = nil
        return true
    }

    public func cancel(_ attempt: UUID) {
        guard activeAttempt == attempt else { return }
        activeAttempt = nil
    }
}
