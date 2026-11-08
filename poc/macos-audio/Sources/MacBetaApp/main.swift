import MacAudioPOC
import Observation
import SwiftUI

@main
@available(macOS 14.0, *)
struct PersonalAssistantBetaApp: App {
    @State private var model: BetaChatModel?
    @State private var configurationError: String?

    init() {
        do {
            let configuration = try BackendLifecycleConfiguration.resolve(
                environment: ProcessInfo.processInfo.environment
            )
            _model = State(initialValue: BetaChatModel(configuration: configuration))
            _configurationError = State(initialValue: nil)
        } catch {
            _model = State(initialValue: nil)
            _configurationError = State(initialValue: "无法找到本机运行环境。请从仓库 scripts/run_beta_app.sh 启动。")
        }
    }

    var body: some Scene {
        WindowGroup("个人 AI 助理测试版") {
            if let model {
                BetaChatView(model: model)
                    .frame(minWidth: 700, minHeight: 540)
                    .task { await model.start() }
                    .onDisappear { Task { await model.shutdown() } }
            } else {
                ContentUnavailableView(
                    "测试版尚未配置",
                    systemImage: "wrench.and.screwdriver",
                    description: Text(configurationError ?? "请检查本机环境配置。")
                )
                .frame(minWidth: 480, minHeight: 220)
            }
        }
    }
}

@available(macOS 14.0, *)
@MainActor
@Observable
final class BetaChatModel {
    private let supervisor: LocalBackendSupervisor
    private var client: LocalAPIClient?
    private var activeRequest: Task<Void, Never>?
    private(set) var status = "正在连接本机服务…"
    private(set) var messages: [LocalChatMessage] = []
    var draft = ""

    var isStreaming: Bool { activeRequest != nil }

    init(configuration: BackendLifecycleConfiguration) {
        supervisor = LocalBackendSupervisor(
            pythonExecutableURL: configuration.pythonExecutableURL,
            backendDirectoryURL: configuration.backendDirectoryURL
        )
    }

    func start() async {
        guard client == nil else { return }
        do {
            let backendSupervisor = supervisor
            let handshake = try await Task.detached { try backendSupervisor.start() }.value
            let localClient = try LocalAPIClient(baseURL: handshake.baseURL, token: handshake.token)
            guard try await localClient.health() else { throw LocalAPIClientError.invalidResponse }
            client = localClient
            status = "已连接本机模型 qwen3.5:0.8b（Ollama）"
        } catch {
            status = "本机服务启动失败：\(error.localizedDescription)"
        }
    }

    func send() {
        guard activeRequest == nil, let client else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        messages.append(LocalChatMessage(role: "user", content: text))
        messages.append(LocalChatMessage(role: "assistant", content: ""))
        let context = Array(messages.dropLast())
        status = "正在生成…"
        activeRequest = Task { [weak self] in
            do {
                for try await delta in client.streamChat(messages: context) {
                    guard let self else { return }
                    if !Task.isCancelled, let index = self.messages.indices.last {
                        self.messages[index] = LocalChatMessage(
                            role: "assistant", content: self.messages[index].content + delta
                        )
                    }
                }
                self?.status = "已连接本机模型 qwen3.5:0.8b（Ollama）"
            } catch is CancellationError {
                self?.status = "已停止本轮生成"
            } catch {
                self?.status = "本机模型请求失败：\(error.localizedDescription)"
            }
            self?.activeRequest = nil
        }
    }

    func stop() {
        activeRequest?.cancel()
        activeRequest = nil
        status = "已停止本轮生成"
    }

    func shutdown() async {
        activeRequest?.cancel()
        activeRequest = nil
        client = nil
        do {
            let backendSupervisor = supervisor
            try await Task.detached { try backendSupervisor.stop() }.value
        } catch {
            status = "本机服务停止异常：\(error.localizedDescription)"
        }
    }
}

@available(macOS 14.0, *)
private struct BetaChatView: View {
    @Bindable var model: BetaChatModel

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("个人 AI 助理").font(.title2.bold())
                    Text(model.status).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("本机模型 · 不保存对话")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        if model.messages.isEmpty {
                            ContentUnavailableView(
                                "开始一段对话",
                                systemImage: "bubble.left.and.bubble.right",
                                description: Text("文字只发送到本机 Ollama；关闭窗口后对话不会保存。")
                            )
                            .padding(.top, 80)
                        }
                        ForEach(Array(model.messages.enumerated()), id: \.offset) { index, message in
                            HStack(alignment: .top) {
                                if message.role == "assistant" { responseBubble(message.content) }
                                else { Spacer(minLength: 80); userBubble(message.content) }
                            }
                            .id(index)
                        }
                    }
                    .padding()
                }
                .onChange(of: model.messages.count) { _, _ in
                    guard !model.messages.isEmpty else { return }
                    proxy.scrollTo(model.messages.count - 1, anchor: .bottom)
                }
            }
            Divider()
            HStack(alignment: .bottom, spacing: 10) {
                TextField("输入消息…", text: $model.draft, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(model.send)
                if model.isStreaming {
                    Button("停止", action: model.stop)
                        .keyboardShortcut(.cancelAction)
                } else {
                    Button("发送", action: model.send)
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .padding()
        }
    }

    private func userBubble(_ text: String) -> some View {
        Text(text).textSelection(.enabled).padding(12)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }

    private func responseBubble(_ text: String) -> some View {
        HStack(alignment: .top) {
            Text(text.isEmpty ? "…" : text).textSelection(.enabled).padding(12)
                .background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                .frame(maxWidth: 560, alignment: .leading)
            Spacer(minLength: 80)
        }
    }
}
