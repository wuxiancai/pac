import Foundation
import Testing
@testable import MacAudioPOC

@MainActor
private final class DeferredAuthorizer: CancellableSensitiveActionAuthorizing {
    private var continuation: CheckedContinuation<Void, Error>?
    private(set) var reason: String?
    private(set) var cancelCount = 0

    func authorize(reason: String) async throws {
        self.reason = reason
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
        }
    }

    func succeed() {
        continuation?.resume()
        continuation = nil
    }

    func deny() {
        continuation?.resume(throwing: TestAuthorizationFailure.denied)
        continuation = nil
    }

    func cancel() { cancelCount += 1 }
}

private enum TestAuthorizationFailure: Error { case denied }
private enum TestRestoreFailure: Error { case invalidBackup }
private let restoreFixtureValue = "fixture-only-value"

private actor FakeBackupRestorer: EncryptedBackupRestoreCalling {
    private(set) var calls: [(String, String)] = []

    func restoreEncryptedBackup(sourcePath: String, password: String) async throws -> String {
        calls.append((sourcePath, password))
        return "pre-restore.sqlcipher"
    }

    func callCount() -> Int { calls.count }
    func lastCall() -> (String, String)? { calls.last }
}

private actor FailingBackupRestorer: EncryptedBackupRestoreCalling {
    private(set) var callCount = 0

    func restoreEncryptedBackup(sourcePath: String, password: String) async throws -> String {
        callCount += 1
        throw TestRestoreFailure.invalidBackup
    }
}

@available(macOS 14.0, *)
@Test @MainActor func backupRestoreCoordinatorAuthorizesBeforeCallingRestoreEndpoint() async throws {
    let authorizer = DeferredAuthorizer()
    let restorer = FakeBackupRestorer()
    let coordinator = EncryptedBackupRestoreCoordinator(authorizer: authorizer, restorer: restorer)
    var authenticationCompleted = false

    let operation = Task {
        try await coordinator.restore(
            sourcePath: "/tmp/synthetic.pacbackup",
            password: restoreFixtureValue,
            timeout: .seconds(2),
            onTimeout: {},
            onAuthenticationCompleted: { authenticationCompleted = true }
        )
    }
    while authorizer.reason == nil { await Task.yield() }

    #expect(authorizer.reason == "恢复本机加密数据")
    #expect(await restorer.callCount() == 0)
    #expect(!authenticationCompleted)

    authorizer.succeed()
    #expect(try await operation.value == "pre-restore.sqlcipher")
    #expect(authenticationCompleted)
    #expect(await restorer.callCount() == 1)
    #expect(await restorer.lastCall()?.0 == "/tmp/synthetic.pacbackup")
    #expect(await restorer.lastCall()?.1 == restoreFixtureValue)
}

@available(macOS 14.0, *)
@Test @MainActor func backupRestoreCoordinatorDoesNotCallEndpointWhenAuthenticationIsDenied() async {
    let authorizer = DeferredAuthorizer()
    let restorer = FakeBackupRestorer()
    let coordinator = EncryptedBackupRestoreCoordinator(authorizer: authorizer, restorer: restorer)

    let operation = Task {
        try await coordinator.restore(
            sourcePath: "/tmp/synthetic.pacbackup",
            password: restoreFixtureValue,
            timeout: .seconds(2),
            onTimeout: {},
            onAuthenticationCompleted: {}
        )
    }
    while authorizer.reason == nil { await Task.yield() }
    authorizer.deny()

    await #expect(throws: TestAuthorizationFailure.denied) { try await operation.value }
    #expect(await restorer.callCount() == 0)
}

@available(macOS 14.0, *)
@Test @MainActor func backupRestoreCoordinatorPropagatesRestoreFailureAfterAuthentication() async {
    let authorizer = DeferredAuthorizer()
    let restorer = FailingBackupRestorer()
    let coordinator = EncryptedBackupRestoreCoordinator(authorizer: authorizer, restorer: restorer)
    var authenticationCompleted = false

    let operation = Task {
        try await coordinator.restore(
            sourcePath: "/tmp/synthetic.pacbackup",
            password: restoreFixtureValue,
            timeout: .seconds(2),
            onTimeout: {},
            onAuthenticationCompleted: { authenticationCompleted = true }
        )
    }
    while authorizer.reason == nil { await Task.yield() }
    authorizer.succeed()

    await #expect(throws: TestRestoreFailure.invalidBackup) { try await operation.value }
    #expect(authenticationCompleted)
    #expect(await restorer.callCount == 1)
}

@available(macOS 14.0, *)
@Test @MainActor func backupRestoreCoordinatorRejectsLateAuthenticationAfterTimeout() async throws {
    let authorizer = DeferredAuthorizer()
    let restorer = FakeBackupRestorer()
    let coordinator = EncryptedBackupRestoreCoordinator(authorizer: authorizer, restorer: restorer)
    var timedOut = false
    var authenticationCompleted = false

    let operation = Task {
        try await coordinator.restore(
            sourcePath: "/tmp/synthetic.pacbackup",
            password: restoreFixtureValue,
            timeout: .milliseconds(10),
            onTimeout: { timedOut = true },
            onAuthenticationCompleted: { authenticationCompleted = true }
        )
    }
    while authorizer.reason == nil { await Task.yield() }
    try await Task.sleep(for: .milliseconds(30))

    #expect(timedOut)
    #expect(authorizer.cancelCount == 1)
    #expect(try await operation.value == nil)
    authorizer.succeed()
    #expect(!authenticationCompleted)
    #expect(await restorer.callCount() == 0)
}

@available(macOS 14.0, *)
@Test @MainActor func backupRestoreCoordinatorRejectsLateAuthenticationAfterUserCancellation() async throws {
    let authorizer = DeferredAuthorizer()
    let restorer = FakeBackupRestorer()
    let coordinator = EncryptedBackupRestoreCoordinator(authorizer: authorizer, restorer: restorer)

    let operation = Task {
        try await coordinator.restore(
            sourcePath: "/tmp/synthetic.pacbackup",
            password: restoreFixtureValue,
            timeout: .seconds(2),
            onTimeout: {},
            onAuthenticationCompleted: {}
        )
    }
    while authorizer.reason == nil { await Task.yield() }

    coordinator.cancelAuthentication()
    #expect(authorizer.cancelCount == 1)
    #expect(try await operation.value == nil)
    authorizer.succeed()
    #expect(await restorer.callCount() == 0)
}
