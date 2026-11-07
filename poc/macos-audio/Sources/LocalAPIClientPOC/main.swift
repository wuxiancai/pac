import Foundation
import MacAudioPOC

@main
@available(macOS 12.0, *)
enum LocalAPIClientPOC {
    static func main() async {
        guard CommandLine.arguments.count == 2,
              let url = URL(string: CommandLine.arguments[1]),
              let token = readLine(),
              !token.isEmpty
        else {
            FileHandle.standardError.write(Data("local API POC input invalid\n".utf8))
            exit(EXIT_FAILURE)
        }

        do {
            let client = try LocalAPIClient(baseURL: url, token: token)
            guard try await client.health() else {
                FileHandle.standardError.write(Data("local API health check failed\n".utf8))
                exit(EXIT_FAILURE)
            }
            FileHandle.standardOutput.write(Data("local health OK\n".utf8))
        } catch {
            FileHandle.standardError.write(Data("local API request failed\n".utf8))
            exit(EXIT_FAILURE)
        }
    }
}
