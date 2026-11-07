import Testing
@testable import MacAudioPOC

@available(macOS 14.0, *)
@MainActor
private final class FakeLocalAPIHealthClient: LocalAPIHealthChecking {
    var result = true
    var shouldThrow = false

    func health() async throws -> Bool {
        if shouldThrow { throw TestLocalAPIError.failed }
        return result
    }
}

private enum TestLocalAPIError: Error {
    case failed
}

@available(macOS 12.0, *)
@MainActor
@Test func localAPIConnectionModelReportsConnectedAndFailedStates() async {
    let client = FakeLocalAPIHealthClient()
    let model = LocalAPIConnectionModel(client: client)

    await model.checkConnection()
    #expect(model.state == .connected)

    client.result = false
    await model.checkConnection()
    #expect(model.state == .unhealthy)

    client.shouldThrow = true
    await model.checkConnection()
    #expect(model.state == .failed)
}
