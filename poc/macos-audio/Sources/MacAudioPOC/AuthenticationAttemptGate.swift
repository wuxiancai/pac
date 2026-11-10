import Foundation

/// Prevents a cancelled or superseded authentication callback from authorizing
/// a sensitive operation after a later UI action has taken over.
@MainActor
@available(macOS 14.0, *)
public final class AuthenticationAttemptGate {
    private var activeAttempt: UUID?
    private var timeoutTask: Task<Void, Never>?

    public init() {}

    @discardableResult
    public func begin(
        timeout: Duration? = nil,
        onTimeout: (@MainActor @Sendable () -> Void)? = nil
    ) -> UUID {
        timeoutTask?.cancel()
        timeoutTask = nil
        let attempt = UUID()
        activeAttempt = attempt
        if let timeout, let onTimeout {
            timeoutTask = Task { [weak self] in
                do {
                    try await Task.sleep(for: timeout)
                } catch {
                    return
                }
                guard let self, self.claim(attempt) else { return }
                onTimeout()
            }
        }
        return attempt
    }

    public func claim(_ attempt: UUID) -> Bool {
        guard activeAttempt == attempt else { return false }
        activeAttempt = nil
        timeoutTask?.cancel()
        timeoutTask = nil
        return true
    }

    public func cancel(_ attempt: UUID) {
        guard activeAttempt == attempt else { return }
        activeAttempt = nil
        timeoutTask?.cancel()
        timeoutTask = nil
    }
}
