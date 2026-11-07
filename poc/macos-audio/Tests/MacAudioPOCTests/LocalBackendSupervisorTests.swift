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
