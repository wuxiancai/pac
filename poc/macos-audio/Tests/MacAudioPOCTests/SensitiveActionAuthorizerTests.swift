import LocalAuthentication
import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeDeviceAuthenticationEvaluator: DeviceAuthenticationEvaluating {
    var isAvailable = true
    var shouldDeny = false
    private(set) var evaluatedPolicy: LAPolicy?
    private(set) var evaluatedReason: String?

    func canEvaluate(policy: LAPolicy) -> Bool {
        evaluatedPolicy = policy
        return isAvailable
    }

    func evaluate(policy: LAPolicy, reason: String) async throws {
        evaluatedPolicy = policy
        evaluatedReason = reason
        if shouldDeny { throw TestAuthenticationError.denied }
    }
}

private enum TestAuthenticationError: Error {
    case denied
}

@MainActor
@Test func sensitiveActionAuthenticationAcceptsBiometricsOrDevicePasscode() {
    #expect(
        TouchIDAuthorizer.authenticationPolicy.rawValue
            == LAPolicy.deviceOwnerAuthentication.rawValue
    )
}

@MainActor
@Test func authorizerUsesSystemAuthenticationWithReason() async throws {
    let evaluator = FakeDeviceAuthenticationEvaluator()
    let authorizer = TouchIDAuthorizer(evaluator: evaluator)

    try await authorizer.authorize(reason: "保存模型服务凭据")

    #expect(evaluator.evaluatedPolicy?.rawValue == LAPolicy.deviceOwnerAuthentication.rawValue)
    #expect(evaluator.evaluatedReason == "保存模型服务凭据")
}

@MainActor
@Test func authorizerRejectsWhenDeviceAuthenticationIsUnavailable() async {
    let evaluator = FakeDeviceAuthenticationEvaluator()
    evaluator.isAvailable = false
    let authorizer = TouchIDAuthorizer(evaluator: evaluator)

    await #expect(throws: SensitiveActionAuthorizationError.authenticationUnavailable) {
        try await authorizer.authorize(reason: "导出记忆")
    }
    #expect(evaluator.evaluatedReason == nil)
}

@MainActor
@Test func authorizerPropagatesSystemDenial() async {
    let evaluator = FakeDeviceAuthenticationEvaluator()
    evaluator.shouldDeny = true
    let authorizer = TouchIDAuthorizer(evaluator: evaluator)

    await #expect(throws: TestAuthenticationError.denied) {
        try await authorizer.authorize(reason: "备份恢复")
    }
    #expect(evaluator.evaluatedReason == "备份恢复")
}
