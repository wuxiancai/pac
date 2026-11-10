import Testing
@testable import MacAudioPOC

@MainActor
@available(macOS 14.0, *)
@Test func cancelledAuthenticationAttemptCannotClaimLateSuccess() {
    let gate = AuthenticationAttemptGate()
    let attempt = gate.begin()

    gate.cancel(attempt)

    #expect(!gate.claim(attempt))
}

@MainActor
@available(macOS 14.0, *)
@Test func newerAuthenticationAttemptRejectsSupersededCallback() {
    let gate = AuthenticationAttemptGate()
    let oldAttempt = gate.begin()
    let currentAttempt = gate.begin()

    #expect(!gate.claim(oldAttempt))
    #expect(gate.claim(currentAttempt))
    #expect(!gate.claim(currentAttempt))
}

@MainActor
@available(macOS 14.0, *)
@Test func timedOutAuthenticationAttemptExpiresAndRunsTimeoutHandler() async throws {
    let gate = AuthenticationAttemptGate()
    var didTimeOut = false
    let attempt = gate.begin(timeout: .milliseconds(20)) {
        didTimeOut = true
    }

    try await Task.sleep(for: .milliseconds(100))

    #expect(didTimeOut)
    #expect(!gate.claim(attempt))
}

@MainActor
@available(macOS 14.0, *)
@Test func claimingAuthenticationAttemptCancelsItsTimeoutHandler() async throws {
    let gate = AuthenticationAttemptGate()
    var didTimeOut = false
    let attempt = gate.begin(timeout: .milliseconds(20)) {
        didTimeOut = true
    }

    #expect(gate.claim(attempt))
    try await Task.sleep(for: .milliseconds(100))

    #expect(!didTimeOut)
}
