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

@available(macOS 14.0, *)
@MainActor
private final class FakeLocalBackendController: LocalBackendControlling {
    let client: any LocalAPIHealthChecking
    var startCount = 0
    var stopCount = 0
    var shouldFailStart = false

    init(client: any LocalAPIHealthChecking) {
        self.client = client
    }

    func startBackend() async throws -> any LocalAPIHealthChecking {
        startCount += 1
        if shouldFailStart { throw TestLocalAPIError.failed }
        return client
    }

    func stopBackend() async throws {
        stopCount += 1
    }
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

@available(macOS 14.0, *)
@MainActor
@Test func localAPIConnectionModelStartsAndStopsManagedBackend() async {
    let health = FakeLocalAPIHealthClient()
    let controller = FakeLocalBackendController(client: health)
    let model = LocalAPIConnectionModel(backendController: controller)

    await model.startBackend()
    #expect(model.state == .connected)
    #expect(controller.startCount == 1)

    await model.stopBackend()
    #expect(model.state == .notChecked)
    #expect(controller.stopCount == 1)
}

@available(macOS 14.0, *)
@MainActor
@Test func localAPIConnectionModelReportsBackendStartFailure() async {
    let controller = FakeLocalBackendController(client: FakeLocalAPIHealthClient())
    controller.shouldFailStart = true
    let model = LocalAPIConnectionModel(backendController: controller)

    await model.startBackend()

    #expect(model.state == .failed)
    #expect(controller.stopCount == 1)
}
