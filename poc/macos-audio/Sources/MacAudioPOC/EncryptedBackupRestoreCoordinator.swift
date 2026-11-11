import Foundation

public protocol EncryptedBackupRestoreCalling: Sendable {
    func restoreEncryptedBackup(sourcePath: String, password: String) async throws -> String
}

extension LocalAPIClient: EncryptedBackupRestoreCalling {}

@MainActor
@available(macOS 14.0, *)
public final class EncryptedBackupRestoreCoordinator {
    private let authorizer: any CancellableSensitiveActionAuthorizing
    private let restorer: any EncryptedBackupRestoreCalling
    private let authenticationGate = AuthenticationAttemptGate()
    private var activeAttempt: UUID?
    private var activeContinuation: CheckedContinuation<String?, Error>?
    private var authenticationTask: Task<Void, Never>?

    public init(
        authorizer: any CancellableSensitiveActionAuthorizing,
        restorer: any EncryptedBackupRestoreCalling
    ) {
        self.authorizer = authorizer
        self.restorer = restorer
    }

    /// Returns nil if authentication was cancelled, timed out, or superseded.
    /// In those cases the restore endpoint is never called.
    public func restore(
        sourcePath: String,
        password: String,
        timeout: Duration = .seconds(60),
        onTimeout: @escaping @MainActor @Sendable () -> Void,
        onAuthenticationCompleted: @escaping @MainActor @Sendable () -> Void
    ) async throws -> String? {
        guard activeAttempt == nil else { return nil }
        return try await withCheckedThrowingContinuation { continuation in
            let attempt = authenticationGate.begin(timeout: timeout) { [weak self] in
                guard let self,
                      self.activeAttempt != nil,
                      let activeContinuation = self.activeContinuation
                else { return }
                self.activeAttempt = nil
                self.activeContinuation = nil
                self.authenticationTask?.cancel()
                self.authenticationTask = nil
                self.authorizer.cancel()
                onTimeout()
                activeContinuation.resume(returning: nil)
            }
            activeAttempt = attempt
            activeContinuation = continuation
            authenticationTask = Task { [weak self] in
                await self?.runAuthentication(
                    attempt: attempt,
                    sourcePath: sourcePath,
                    password: password,
                    onAuthenticationCompleted: onAuthenticationCompleted
                )
            }
        }
    }

    private func runAuthentication(
        attempt: UUID,
        sourcePath: String,
        password: String,
        onAuthenticationCompleted: @MainActor @Sendable () -> Void
    ) async {
        do {
            try await authorizer.authorize(reason: "恢复本机加密数据")
        } catch {
            guard authenticationGate.claim(attempt) else { return }
            finish(attempt, with: .failure(error))
            return
        }

        guard authenticationGate.claim(attempt) else { return }
        onAuthenticationCompleted()
        do {
            let prebackupPath = try await restorer.restoreEncryptedBackup(
                sourcePath: sourcePath,
                password: password
            )
            finish(attempt, with: .success(prebackupPath))
        } catch {
            finish(attempt, with: .failure(error))
        }
    }

    private func finish(_ attempt: UUID, with result: Result<String?, Error>) {
        guard activeAttempt == attempt, let continuation = activeContinuation else { return }
        activeAttempt = nil
        activeContinuation = nil
        authenticationTask = nil
        continuation.resume(with: result)
    }

    public func cancelAuthentication() {
        guard let attempt = activeAttempt,
              let continuation = activeContinuation
        else { return }
        authenticationGate.cancel(attempt)
        activeAttempt = nil
        activeContinuation = nil
        authenticationTask?.cancel()
        authenticationTask = nil
        authorizer.cancel()
        continuation.resume(returning: nil)
    }
}
