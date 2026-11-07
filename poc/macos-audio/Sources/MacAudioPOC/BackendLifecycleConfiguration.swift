import Foundation

public struct BackendLifecycleConfiguration: Equatable, Sendable {
    public let pythonExecutableURL: URL
    public let backendDirectoryURL: URL

    public static func resolve(environment: [String: String]) throws -> Self {
        guard let pythonPath = environment["PAC_POC_PYTHON"], !pythonPath.isEmpty else {
            throw BackendLifecycleConfigurationError.missingPythonRuntime
        }
        guard let backendPath = environment["PAC_POC_BACKEND"], !backendPath.isEmpty else {
            throw BackendLifecycleConfigurationError.missingBackendDirectory
        }

        let python = URL(fileURLWithPath: pythonPath).standardizedFileURL
        let backend = URL(fileURLWithPath: backendPath, isDirectory: true).standardizedFileURL
        guard FileManager.default.isExecutableFile(atPath: python.path) else {
            throw BackendLifecycleConfigurationError.invalidPythonRuntime
        }
        guard FileManager.default.fileExists(
            atPath: backend.appendingPathComponent("pac_poc/local_service.py").path
        ) else {
            throw BackendLifecycleConfigurationError.missingBackendModule
        }
        return Self(pythonExecutableURL: python, backendDirectoryURL: backend)
    }
}

public enum BackendLifecycleConfigurationError: Error, Equatable {
    case missingPythonRuntime
    case invalidPythonRuntime
    case missingBackendDirectory
    case missingBackendModule
}
