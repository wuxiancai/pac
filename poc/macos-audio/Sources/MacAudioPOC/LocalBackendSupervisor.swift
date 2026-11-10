import Darwin
import Foundation

public struct LocalBackendHandshake: Sendable {
    public let baseURL: URL
    public let token: String
}

public enum LocalBackendSupervisorError: Error, Equatable {
    case alreadyRunning
    case backendRuntimeUnavailable
    case launchFailed
    case databaseKeyDeliveryFailed
    case startupTimedOut
    case invalidHandshake
    case shutdownTimedOut
}

/// Owns only the fixed `pac_poc.local_service` module through private standard pipes.
@available(macOS 12.0, *)
public final class LocalBackendSupervisor: @unchecked Sendable {
    private let lifecycleLock = NSLock()
    private let pythonExecutableURL: URL
    private let backendDirectoryURL: URL
    private let startupTimeout: TimeInterval
    private let shutdownTimeout: TimeInterval
    private var process: Process?
    private var inputPipe: Pipe?

    public init(
        pythonExecutableURL: URL,
        backendDirectoryURL: URL,
        startupTimeout: TimeInterval = 5,
        shutdownTimeout: TimeInterval = 5
    ) {
        self.pythonExecutableURL = pythonExecutableURL
        self.backendDirectoryURL = backendDirectoryURL
        self.startupTimeout = max(0.1, startupTimeout)
        self.shutdownTimeout = max(0.1, shutdownTimeout)
    }

    deinit {
        try? stop()
    }

    public var isRunning: Bool {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        return process?.isRunning ?? false
    }

    public func start(databaseKey: Data? = nil) throws -> LocalBackendHandshake {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        if let process {
            guard !process.isRunning else { throw LocalBackendSupervisorError.alreadyRunning }
            inputPipe?.fileHandleForWriting.closeFile()
            self.process = nil
            inputPipe = nil
        }
        guard FileManager.default.isExecutableFile(atPath: pythonExecutableURL.path),
              FileManager.default.fileExists(
                atPath: backendDirectoryURL.appendingPathComponent("pac_poc/local_service.py").path
              )
        else {
            throw LocalBackendSupervisorError.backendRuntimeUnavailable
        }

        if let databaseKey, databaseKey.count != DatabaseKeychainStore.keyLength {
            throw LocalBackendSupervisorError.databaseKeyDeliveryFailed
        }
        let child = Process()
        let childInput = Pipe()
        let childOutput = Pipe()
        child.executableURL = pythonExecutableURL
        child.arguments = ["-m", "pac_poc.local_service"]
        if databaseKey != nil {
            child.arguments?.append("--database-key-stdin")
        }
        child.currentDirectoryURL = backendDirectoryURL
        child.environment = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        ]
        child.standardInput = childInput
        child.standardOutput = childOutput
        child.standardError = FileHandle.nullDevice

        do {
            try child.run()
        } catch {
            childInput.fileHandleForWriting.closeFile()
            childInput.fileHandleForReading.closeFile()
            childOutput.fileHandleForReading.closeFile()
            childOutput.fileHandleForWriting.closeFile()
            throw LocalBackendSupervisorError.launchFailed
        }
        childInput.fileHandleForReading.closeFile()
        childOutput.fileHandleForWriting.closeFile()
        if let databaseKey {
            do {
                try childInput.fileHandleForWriting.write(contentsOf: Data(databaseKey.hexadecimal.utf8) + Data([0x0A]))
            } catch {
                childInput.fileHandleForWriting.closeFile()
                Self.stopUnreadyProcess(child, timeout: shutdownTimeout)
                childOutput.fileHandleForReading.closeFile()
                throw LocalBackendSupervisorError.databaseKeyDeliveryFailed
            }
        }

        do {
            let line = try Self.readLine(
                from: childOutput.fileHandleForReading,
                timeout: startupTimeout
            )
            let handshake = try Self.decodeHandshake(line)
            process = child
            inputPipe = childInput
            childOutput.fileHandleForReading.closeFile()
            return handshake
        } catch {
            childInput.fileHandleForWriting.closeFile()
            Self.stopUnreadyProcess(child, timeout: shutdownTimeout)
            childOutput.fileHandleForReading.closeFile()
            throw error
        }
    }

    public func stop() throws {
        lifecycleLock.lock()
        defer { lifecycleLock.unlock() }
        guard let child = process else { return }
        // EOF is the graceful stop signal and cannot raise SIGPIPE if the child exited.
        inputPipe?.fileHandleForWriting.closeFile()
        guard Self.waitForExit(child, timeout: shutdownTimeout) else {
            child.terminate()
            guard Self.waitForExit(child, timeout: 1) else {
                _ = Darwin.kill(child.processIdentifier, SIGKILL)
                _ = Self.waitForExit(child, timeout: 1)
                process = nil
                inputPipe = nil
                throw LocalBackendSupervisorError.shutdownTimedOut
            }
            process = nil
            inputPipe = nil
            throw LocalBackendSupervisorError.shutdownTimedOut
        }
        process = nil
        inputPipe = nil
    }

    private static func decodeHandshake(_ data: Data) throws -> LocalBackendHandshake {
        guard let object = try? JSONSerialization.jsonObject(with: data),
              let values = object as? [String: String],
              Set(values.keys) == Set(["base_url", "token"]),
              let endpoint = values["base_url"],
              let url = URL(string: endpoint),
              let token = values["token"],
              token.count >= 32,
              (try? LocalAPIClient(baseURL: url, token: token)) != nil
        else {
            throw LocalBackendSupervisorError.invalidHandshake
        }
        return LocalBackendHandshake(baseURL: url, token: token)
    }

    private static func readLine(from handle: FileHandle, timeout: TimeInterval) throws -> Data {
        let descriptor = handle.fileDescriptor
        let deadline = ProcessInfo.processInfo.systemUptime + timeout
        var data = Data()
        while ProcessInfo.processInfo.systemUptime < deadline {
            let remaining = max(0.001, deadline - ProcessInfo.processInfo.systemUptime)
            var watched = pollfd(fd: descriptor, events: Int16(POLLIN | POLLHUP), revents: 0)
            let result = Darwin.poll(&watched, 1, Int32(remaining * 1_000))
            if result == 0 { throw LocalBackendSupervisorError.startupTimedOut }
            if result < 0 {
                if errno == EINTR { continue }
                throw LocalBackendSupervisorError.invalidHandshake
            }

            var bytes = [UInt8](repeating: 0, count: 1024)
            let count = Darwin.read(descriptor, &bytes, bytes.count)
            guard count > 0 else { throw LocalBackendSupervisorError.invalidHandshake }
            data.append(contentsOf: bytes.prefix(count))
            if let newline = data.firstIndex(of: 0x0A) {
                guard newline == data.index(before: data.endIndex) else {
                    throw LocalBackendSupervisorError.invalidHandshake
                }
                return data[..<newline]
            }
            guard data.count <= 4096 else { throw LocalBackendSupervisorError.invalidHandshake }
        }
        throw LocalBackendSupervisorError.startupTimedOut
    }

    private static func waitForExit(_ process: Process, timeout: TimeInterval) -> Bool {
        let deadline = ProcessInfo.processInfo.systemUptime + timeout
        while process.isRunning && ProcessInfo.processInfo.systemUptime < deadline {
            usleep(10_000)
        }
        return !process.isRunning
    }

    private static func stopUnreadyProcess(_ process: Process, timeout: TimeInterval) {
        guard process.isRunning else { return }
        process.terminate()
        if !waitForExit(process, timeout: timeout) {
            _ = Darwin.kill(process.processIdentifier, SIGKILL)
            _ = waitForExit(process, timeout: 1)
        }
    }
}

private extension Data {
    var hexadecimal: String { map { String(format: "%02x", $0) }.joined() }
}
