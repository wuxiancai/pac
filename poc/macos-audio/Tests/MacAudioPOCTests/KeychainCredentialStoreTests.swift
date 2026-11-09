import Foundation
import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeSensitiveActionAuthorizer: SensitiveActionAuthorizing {
    var shouldDeny = false
    private(set) var requestedReasons: [String] = []

    func authorize(reason: String) async throws {
        requestedReasons.append(reason)
        if shouldDeny { throw TestAuthorizationError.denied }
    }
}

private enum TestAuthorizationError: Error {
    case denied
}

@Test func keychainCredentialCanBeStoredAndDeletedWithoutReadAPI() throws {
    let service = "pac-poc-test-\(UUID().uuidString)"
    let store = KeychainCredentialStore(service: service)
    defer { try? store.delete(account: "provider-api-key") }

    #expect(try !store.contains(account: "provider-api-key"))
    try store.save("dummy-secret-for-test", account: "provider-api-key")
    #expect(try store.contains(account: "provider-api-key"))
    try store.delete(account: "provider-api-key")
    #expect(try !store.contains(account: "provider-api-key"))
}

@Test func keychainDeleteIsIdempotent() throws {
    let store = KeychainCredentialStore(service: "pac-poc-test-\(UUID().uuidString)")

    try store.delete(account: "missing")
}

@Test func keychainRejectsEmptyCredentialIdentity() {
    let store = KeychainCredentialStore(service: "pac-poc-test")

    #expect(throws: KeychainCredentialError.emptyIdentity) {
        try store.save("secret", account: " ")
    }
}

@Test func keychainRejectsEmptySecretAndAllowsCredentialRotation() throws {
    let service = "pac-poc-test-\(UUID().uuidString)"
    let store = KeychainCredentialStore(service: service)
    defer { try? store.delete(account: "provider") }

    #expect(throws: KeychainCredentialError.emptyCredential) {
        try store.save("", account: "provider")
    }
    try store.save("old-dummy-secret", account: "provider")
    try store.save("new-dummy-secret", account: "provider")
    #expect(try store.contains(account: "provider"))
}

@MainActor
@Test func credentialManagementRequiresAuthorizationBeforeSaving() async throws {
    let serviceName = "pac-poc-test-\(UUID().uuidString)"
    let store = KeychainCredentialStore(service: serviceName)
    let authorizer = FakeSensitiveActionAuthorizer()
    authorizer.shouldDeny = true
    let manager = CredentialManagementService(service: serviceName, authorizer: authorizer)

    await #expect(throws: TestAuthorizationError.denied) {
        try await manager.save("dummy-secret", account: "provider")
    }
    #expect(try !store.contains(account: "provider"))

    authorizer.shouldDeny = false
    try await manager.save("dummy-secret", account: "provider")
    #expect(try store.contains(account: "provider"))
    #expect(authorizer.requestedReasons.count == 2)
    try store.delete(account: "provider")
}

@MainActor
@Test func credentialDeletionAlsoRequiresAuthorization() async throws {
    let serviceName = "pac-poc-test-\(UUID().uuidString)"
    let store = KeychainCredentialStore(service: serviceName)
    let account = "provider"
    try store.save("dummy-secret", account: account)
    defer { try? store.delete(account: account) }

    let authorizer = FakeSensitiveActionAuthorizer()
    authorizer.shouldDeny = true
    let manager = CredentialManagementService(service: serviceName, authorizer: authorizer)

    await #expect(throws: TestAuthorizationError.denied) {
        try await manager.delete(account: account)
    }
    #expect(try store.contains(account: account))

    authorizer.shouldDeny = false
    try await manager.delete(account: account)
    #expect(try !store.contains(account: account))
}
