import Testing
import LocalAuthentication
@testable import MacAudioPOC

@available(macOS 14.0, *)
@MainActor
private final class FakeSensitiveActionAuthorizer: SensitiveActionAuthorizing {
    var errorToThrow: (any Error)?
    private(set) var reasons: [String] = []

    func authorize(reason: String) async throws {
        reasons.append(reason)
        if let errorToThrow { throw errorToThrow }
    }
}

@available(macOS 14.0, *)
@MainActor
@Test func systemAuthenticationTestUsesExplicitNoKeychainReason() async {
    let authorizer = FakeSensitiveActionAuthorizer()
    let model = SystemAuthenticationTestModel(authorizer: authorizer)

    await model.testAuthentication()

    #expect(model.state == .authenticated)
    #expect(authorizer.reasons == ["验证本机系统认证能力；本测试不会修改钥匙串。"])
}

@available(macOS 14.0, *)
@MainActor
@Test func systemAuthenticationTestFailsClosedWhenAuthenticationIsDenied() async {
    let authorizer = FakeSensitiveActionAuthorizer()
    authorizer.errorToThrow = LAError(.authenticationFailed)
    let model = SystemAuthenticationTestModel(authorizer: authorizer)

    await model.testAuthentication()

    #expect(model.state == .notAuthenticated)
}

@available(macOS 14.0, *)
@MainActor
@Test func systemAuthenticationTestDistinguishesUserCancellation() async {
    let authorizer = FakeSensitiveActionAuthorizer()
    authorizer.errorToThrow = LAError(.userCancel)
    let model = SystemAuthenticationTestModel(authorizer: authorizer)

    await model.testAuthentication()

    #expect(model.state == .cancelled)
}

@available(macOS 14.0, *)
@MainActor
@Test func systemAuthenticationTestDistinguishesSystemInterruption() async {
    let authorizer = FakeSensitiveActionAuthorizer()
    authorizer.errorToThrow = LAError(.systemCancel)
    let model = SystemAuthenticationTestModel(authorizer: authorizer)

    await model.testAuthentication()

    #expect(model.state == .interrupted)
}
