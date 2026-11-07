import MacAudioPOC
import SwiftUI

@main
@available(macOS 14.0, *)
struct BackendLifecyclePOCApp: App {
    @State private var supervisor: LocalBackendSupervisor?
    @State private var configurationMessage: String

    init() {
        do {
            let configuration = try BackendLifecycleConfiguration.resolve(
                environment: ProcessInfo.processInfo.environment
            )
            _supervisor = State(initialValue: LocalBackendSupervisor(
                pythonExecutableURL: configuration.pythonExecutableURL,
                backendDirectoryURL: configuration.backendDirectoryURL
            ))
            _configurationMessage = State(initialValue: "")
        } catch {
            _supervisor = State(initialValue: nil)
            _configurationMessage = State(initialValue: "请设置 PAC_POC_PYTHON 与 PAC_POC_BACKEND 本机配置后重启演示程序。")
        }
    }

    var body: some Scene {
        WindowGroup("本机后端生命周期 POC") {
            Group {
                if let supervisor {
                    LocalAPIConnectionView(backendController: supervisor)
                } else {
                    VStack(spacing: 12) {
                        Text("尚未配置本机后端")
                            .font(.headline)
                        Text(configurationMessage)
                            .multilineTextAlignment(.center)
                    }
                    .padding(24)
                }
            }
            .frame(minWidth: 420, minHeight: 180)
        }
    }
}
