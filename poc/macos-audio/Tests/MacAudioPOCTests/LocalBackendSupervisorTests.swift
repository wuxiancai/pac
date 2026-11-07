import Foundation
import Testing
@testable import MacAudioPOC

@available(macOS 12.0, *)
@Test func supervisorStartsFixedLoopbackBackendAndStopsItGracefully() async throws {
    let (python, backendDirectory) = try localBackendFixture()
    let supervisor = LocalBackendSupervisor(
        pythonExecutableURL: python,
        backendDirectoryURL: backendDirectory
    )

    let handshake = try supervisor.start()
    #expect(handshake.baseURL.host == "127.0.0.1")
    #expect(handshake.token.count >= 32)
    #expect(try await LocalAPIClient(baseURL: handshake.baseURL, token: handshake.token).health())
    do {
        _ = try await LocalAPIClient(baseURL: handshake.baseURL, token: "wrong-token").health()
        #expect(Bool(false))
    } catch let error as LocalAPIClientError {
        #expect(error == .requestFailed(statusCode: 401))
    }

    try supervisor.stop()
    #expect(!supervisor.isRunning)
}

@available(macOS 12.0, *)
@Test func supervisorRejectsDuplicateStartAndAllowsStartAfterStop() throws {
    let (python, backendDirectory) = try localBackendFixture()
    let supervisor = LocalBackendSupervisor(
        pythonExecutableURL: python,
        backendDirectoryURL: backendDirectory
    )

    _ = try supervisor.start()
    #expect(throws: LocalBackendSupervisorError.alreadyRunning) {
        _ = try supervisor.start()
    }
    try supervisor.stop()
    _ = try supervisor.start()
    try supervisor.stop()
}

@available(macOS 12.0, *)
@Test func supervisorTimesOutAndTerminatesBackendThatNeverHandshakes() throws {
    let (python, fixtureDirectory) = try localBackendFixture(moduleSource: "import time\ntime.sleep(30)\n")
    defer { try? FileManager.default.removeItem(at: fixtureDirectory) }
    let supervisor = LocalBackendSupervisor(
        pythonExecutableURL: python,
        backendDirectoryURL: fixtureDirectory,
        startupTimeout: 0.25,
        shutdownTimeout: 0.5
    )

    let startedAt = ProcessInfo.processInfo.systemUptime
    #expect(throws: LocalBackendSupervisorError.startupTimedOut) {
        _ = try supervisor.start()
    }
    #expect(ProcessInfo.processInfo.systemUptime - startedAt < 3)
    #expect(!supervisor.isRunning)
}

@available(macOS 12.0, *)
@Test func supervisorRejectsMalformedHandshakeWithoutRetainingChild() throws {
    let (python, fixtureDirectory) = try localBackendFixture(moduleSource: "print('not-json', flush=True)\n")
    defer { try? FileManager.default.removeItem(at: fixtureDirectory) }
    let supervisor = LocalBackendSupervisor(
        pythonExecutableURL: python,
        backendDirectoryURL: fixtureDirectory
    )

    #expect(throws: LocalBackendSupervisorError.invalidHandshake) {
        _ = try supervisor.start()
    }
    #expect(!supervisor.isRunning)
}

@available(macOS 12.0, *)
@Test func supervisorAllowsExplicitRestartAfterChildExited() throws {
    let handshake = #"{"base_url":"http://127.0.0.1:49152","token":"01234567890123456789012345678901"}"#
    let (python, fixtureDirectory) = try localBackendFixture(
        moduleSource: "print('''\(handshake)''', flush=True)\n"
    )
    defer { try? FileManager.default.removeItem(at: fixtureDirectory) }
    let supervisor = LocalBackendSupervisor(
        pythonExecutableURL: python,
        backendDirectoryURL: fixtureDirectory
    )

    _ = try supervisor.start()
    let deadline = ProcessInfo.processInfo.systemUptime + 2
    while supervisor.isRunning && ProcessInfo.processInfo.systemUptime < deadline {
        usleep(10_000)
    }
    #expect(!supervisor.isRunning)
    do {
        _ = try supervisor.start()
    } catch {
        #expect(Bool(false))
    }
    try supervisor.stop()
}

private func localBackendFixture() throws -> (URL, URL) {
    var repositoryRoot = URL(fileURLWithPath: #filePath)
    for _ in 0..<5 {
        repositoryRoot.deleteLastPathComponent()
    }
    let backend = repositoryRoot.appendingPathComponent("backend", isDirectory: true)
    let python = backend.appendingPathComponent(".venv/bin/python")
    guard FileManager.default.isExecutableFile(atPath: python.path),
          FileManager.default.fileExists(
            atPath: backend.appendingPathComponent("pac_poc/local_service.py").path
          )
    else {
        throw LocalBackendSupervisorError.backendRuntimeUnavailable
    }
    return (python, backend)
}

private func localBackendFixture(moduleSource: String) throws -> (URL, URL) {
    var repositoryRoot = URL(fileURLWithPath: #filePath)
    for _ in 0..<5 {
        repositoryRoot.deleteLastPathComponent()
    }
    let backend = repositoryRoot.appendingPathComponent("backend", isDirectory: true)
    let python = backend.appendingPathComponent(".venv/bin/python")
    let fixture = repositoryRoot.appendingPathComponent(
        ".poc-data/swift-supervisor-fixture-\(UUID().uuidString)",
        isDirectory: true
    )
    let package = fixture.appendingPathComponent("pac_poc", isDirectory: true)
    try FileManager.default.createDirectory(at: package, withIntermediateDirectories: true)
    try Data().write(to: package.appendingPathComponent("__init__.py"))
    try Data(moduleSource.utf8).write(to: package.appendingPathComponent("local_service.py"))
    return (python, fixture)
}
