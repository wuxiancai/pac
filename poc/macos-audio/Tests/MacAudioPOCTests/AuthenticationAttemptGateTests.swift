import Testing
@testable import MacAudioPOC

@MainActor
@Test func cancelledAuthenticationAttemptCannotClaimLateSuccess() {
    let gate = AuthenticationAttemptGate()
    let attempt = gate.begin()

    gate.cancel(attempt)

    #expect(!gate.claim(attempt))
}

@MainActor
@Test func newerAuthenticationAttemptRejectsSupersededCallback() {
    let gate = AuthenticationAttemptGate()
    let oldAttempt = gate.begin()
    let currentAttempt = gate.begin()

    #expect(!gate.claim(oldAttempt))
    #expect(gate.claim(currentAttempt))
    #expect(!gate.claim(currentAttempt))
}
