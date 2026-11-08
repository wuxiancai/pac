import MacAudioPOC
import Observation
import SwiftUI

enum ModelSource: String, CaseIterable, Identifiable {
    case local
    case cloud

    var id: String { rawValue }
    var title: String { self == .local ? "本地大模型" : "云端大模型" }
}

enum CloudProvider: String, CaseIterable, Identifiable {
    case deepseek
    case openrouter

    var id: String { rawValue }
    var title: String { self == .deepseek ? "DeepSeek" : "OpenRouter" }
    var account: String { rawValue }
    var region: String { self == .deepseek ? "中国" : "Global（由 OpenRouter 路由）" }
    var model: String {
        switch self {
        case .deepseek: "deepseek-flash"
        case .openrouter: "deepseek/deepseek-v4.1-flash-1017"
        }
    }
}

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
    private var activeRequestID: UUID?
    private let defaults = UserDefaults.standard
    private(set) var status = "正在连接本机服务…"
    private(set) var messages: [LocalChatMessage] = []
    var draft = ""
    var source: ModelSource {
        didSet { defaults.set(source.rawValue, forKey: "beta.model.source") }
    }
    var localModel: String {
        didSet { defaults.set(localModel, forKey: "beta.model.local") }
    }
    var cloudProvider: CloudProvider {
        didSet { defaults.set(cloudProvider.rawValue, forKey: "beta.model.cloud-provider") }
    }

    var isStreaming: Bool { activeRequest != nil }
    var usesCloud: Bool { source == .cloud }
    var selectedProvider: String { usesCloud ? cloudProvider.rawValue : "ollama" }
    var selectedModel: String { usesCloud ? cloudProvider.model : localModel }
    var selectedRegion: String { usesCloud ? cloudProvider.region : "仅本机" }
    var selectedModelTitle: String { usesCloud ? cloudProvider.title : "Ollama 本地模型" }
    var remoteConsentMessages: [LocalChatMessage] {
        nonemptyMessages(messages) + [LocalChatMessage(
            role: "user",
            content: draft.trimmingCharacters(in: .whitespacesAndNewlines)
        )]
    }

    init(configuration: BackendLifecycleConfiguration) {
        source = ModelSource(rawValue: defaults.string(forKey: "beta.model.source") ?? "local") ?? .local
        localModel = defaults.string(forKey: "beta.model.local") ?? "qwen3.5:0.8b"
        cloudProvider = CloudProvider(
            rawValue: defaults.string(forKey: "beta.model.cloud-provider") ?? "deepseek"
        ) ?? .deepseek
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
            status = "本机服务已连接；当前模型：\(selectedModel)"
        } catch {
            status = "本机服务启动失败：\(error.localizedDescription)"
        }
    }

    func send(confirmedForThisRequest: Bool = false) {
        guard activeRequest == nil, let client else { return }
        guard !usesCloud || confirmedForThisRequest else { return }
        guard !selectedModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            status = "请先在模型设置中选择模型。"
            return
        }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        messages.append(LocalChatMessage(role: "user", content: text))
        messages.append(LocalChatMessage(role: "assistant", content: ""))
        let context = nonemptyMessages(Array(messages.dropLast()))
        let provider = selectedProvider
        let modelID = selectedModel
        let requestID = UUID()
        activeRequestID = requestID
        status = "正在使用\(usesCloud ? "云端" : "本地")模型生成…"
        activeRequest = Task { [weak self] in
            do {
                for try await delta in client.streamChat(
                    messages: context,
                    provider: provider,
                    model: modelID,
                    confirmedForThisRequest: confirmedForThisRequest
                ) {
                    guard let self else { return }
                    guard self.activeRequestID == requestID else { return }
                    if !Task.isCancelled, let index = self.messages.indices.last {
                        self.messages[index] = LocalChatMessage(
                            role: "assistant", content: self.messages[index].content + delta
                        )
                    }
                }
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "本机服务已连接；当前模型：\(modelID)"
            } catch is CancellationError {
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "已停止本轮生成"
            } catch {
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "模型请求失败：\(error.localizedDescription)"
            }
            guard let self, self.activeRequestID == requestID else { return }
            self.activeRequest = nil
            self.activeRequestID = nil
        }
    }

    func stop() {
        activeRequest?.cancel()
        activeRequest = nil
        activeRequestID = nil
        status = "已停止本轮生成"
    }

    private func nonemptyMessages(_ values: [LocalChatMessage]) -> [LocalChatMessage] {
        values.filter { $0.role != "assistant" || !$0.content.isEmpty }
    }

    func shutdown() async {
        activeRequest?.cancel()
        activeRequest = nil
        activeRequestID = nil
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
    @State private var showingSettings = false
    @State private var showingCloudConsent = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("个人 AI 助理").font(.title2.bold())
                    Text(model.status).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button { showingSettings = true } label: {
                    Label("模型设置", systemImage: "gearshape")
                }
                .accessibilityIdentifier("model-settings-button")
                Text("对话不保存")
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
                                description: Text(model.usesCloud
                                    ? "发送云端请求前会逐次显示完整对话并等待确认。关闭窗口后对话不会保存。"
                                    : "文字只发送到本机 Ollama；关闭窗口后对话不会保存。")
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
                    .onSubmit(requestSend)
                if model.isStreaming {
                    Button("停止", action: model.stop)
                        .keyboardShortcut(.cancelAction)
                } else {
                    Button("发送", action: requestSend)
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            .padding()
        }
        .sheet(isPresented: $showingSettings) {
            BetaModelSettingsView(model: model)
        }
        .sheet(isPresented: $showingCloudConsent) {
            CloudSendConsentView(
                provider: model.selectedModelTitle,
                model: model.selectedModel,
                region: model.selectedRegion,
                messages: model.remoteConsentMessages,
                onCancel: { showingCloudConsent = false },
                onConfirm: {
                    showingCloudConsent = false
                    model.send(confirmedForThisRequest: true)
                }
            )
        }
    }

    private func requestSend() {
        guard !model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        if model.usesCloud { showingCloudConsent = true }
        else { model.send() }
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

@available(macOS 14.0, *)
private struct BetaModelSettingsView: View {
    @Bindable var model: BetaChatModel
    @Environment(\.dismiss) private var dismiss
    @State private var apiKey = ""
    @State private var keyStatus = ""
    @State private var saveMessage = ""
    private let keychain = KeychainCredentialStore(
        service: "com.personal-ai-assistant.phase0.provider"
    )

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("模型设置").font(.title2.bold())
                Spacer()
                Button("完成") { dismiss() }
            }
            Picker("模型来源", selection: $model.source) {
                ForEach(ModelSource.allCases) { source in
                    Text(source.title).tag(source)
                }
            }
            .pickerStyle(.segmented)

            if model.source == .local {
                TextField("Ollama 模型名称", text: $model.localModel)
                    .textFieldStyle(.roundedBorder)
                Text("例如 qwen3.5:0.8b。模型由本机 Ollama 提供；请填写已安装的模型名称。")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                Picker("云端服务商", selection: $model.cloudProvider) {
                    ForEach(CloudProvider.allCases) { provider in
                        Text(provider.title).tag(provider)
                    }
                }
                .onChange(of: model.cloudProvider) { _, _ in refreshKeyStatus() }
                LabeledContent("模型", value: model.cloudProvider.model)
                LabeledContent("区域", value: model.cloudProvider.region)
                LabeledContent("Keychain", value: keyStatus)
                SecureField("输入 API Key（只保存到本机 Keychain）", text: $apiKey)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    Button("保存 API Key") { saveCredential() }
                        .disabled(apiKey.isEmpty)
                    if !saveMessage.isEmpty {
                        Text(saveMessage).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Text("每次发送云端请求前，应用都会展示完整对话、服务商、模型和区域，并要求单次确认。Key 不进入聊天、设置文件或日志。")
                    .font(.callout).foregroundStyle(.secondary)
                Label("千问 Token Plan 个人版 Key 不能用于本自建应用；如需千问，请先取得适用于自定义应用的 API 凭据。", systemImage: "info.circle")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(24)
        .frame(minWidth: 520, minHeight: 360)
        .task { refreshKeyStatus() }
    }

    private func refreshKeyStatus() {
        do {
            keyStatus = try keychain.contains(account: model.cloudProvider.account)
                ? "已保存（\(model.cloudProvider.account)）"
                : "未配置（\(model.cloudProvider.account)）"
        } catch {
            keyStatus = "无法读取 Keychain 状态"
        }
    }

    private func saveCredential() {
        do {
            try keychain.save(apiKey, account: model.cloudProvider.account)
            apiKey = ""
            saveMessage = "已安全保存。"
            refreshKeyStatus()
        } catch {
            saveMessage = error.localizedDescription
        }
    }
}

@available(macOS 14.0, *)
private struct CloudSendConsentView: View {
    let provider: String
    let model: String
    let region: String
    let messages: [LocalChatMessage]
    let onCancel: () -> Void
    let onConfirm: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("确认发送到云端").font(.title2.bold())
            Text("以下完整对话将发送给 \(provider) 的 \(model)，服务区域：\(region)。按普通个人对话（L2）处理；本次授权仅覆盖这一次请求。L3 凭据会被后端拦截。")
                .fixedSize(horizontal: false, vertical: true)
            Label("不要发送密码、API Key、私钥或其他不应上传的信息。", systemImage: "exclamationmark.triangle")
                .font(.callout).foregroundStyle(.orange)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(Array(messages.enumerated()), id: \.offset) { _, message in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(message.role == "user" ? "用户" : "助手")
                                .font(.caption.bold()).foregroundStyle(.secondary)
                            Text(message.content).textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(10)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
            .frame(minHeight: 150)
            HStack {
                Button("取消", action: onCancel)
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("同意并发送这一次", action: onConfirm)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(minWidth: 580, minHeight: 460)
    }
}
