import Testing
@testable import MacAudioPOC

@available(macOS 14.0, *)
@MainActor
private final class FakeSensitiveActionAuthorizer: SensitiveActionAuthorizing {
    var shouldFail = false
    private(set) var reasons: [String] = []

    func authorize(reason: String) async throws {
        reasons.append(reason)
        if shouldFail { throw TestAuthorizationError.denied }
    }
}

private enum TestAuthorizationError: Error {
    case denied
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
    authorizer.shouldFail = true
    let model = SystemAuthenticationTestModel(authorizer: authorizer)

    await model.testAuthentication()

    #expect(model.state == .notAuthenticated)
}
