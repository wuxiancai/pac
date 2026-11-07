import Foundation
import Testing
@testable import MacAudioPOC

@Test func launchConfigurationAcceptsExplicitPythonAndBackendPaths() throws {
    let (python, backend) = try localBackendPaths()

    let configuration = try BackendLifecycleConfiguration.resolve(environment: [
        "PAC_POC_PYTHON": python.path,
        "PAC_POC_BACKEND": backend.path,
    ])

    #expect(configuration.pythonExecutableURL == python)
    #expect(configuration.backendDirectoryURL == backend)
}

@Test func launchConfigurationFailsClosedWhenRuntimeIsMissing() throws {
    let (_, backend) = try localBackendPaths()

    #expect(throws: BackendLifecycleConfigurationError.missingPythonRuntime) {
        try BackendLifecycleConfiguration.resolve(environment: ["PAC_POC_BACKEND": backend.path])
    }
}

@Test func launchConfigurationFailsClosedWhenBackendModuleIsMissing() throws {
    let (python, _) = try localBackendPaths()

    #expect(throws: BackendLifecycleConfigurationError.missingBackendModule) {
        try BackendLifecycleConfiguration.resolve(environment: [
            "PAC_POC_PYTHON": python.path,
            "PAC_POC_BACKEND": "/path/that/does/not/exist",
        ])
    }
}

private func localBackendPaths() throws -> (URL, URL) {
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
