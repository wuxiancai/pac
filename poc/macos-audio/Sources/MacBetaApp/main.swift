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
    case qwenApp = "qwen-app"
    case deepseek
    case openrouter

    var id: String { rawValue }
    var title: String {
        switch self {
        case .qwenApp: "千问（应用 API）"
        case .deepseek: "DeepSeek"
        case .openrouter: "OpenRouter"
        }
    }
    var account: String { rawValue }
    var region: String { self == .openrouter ? "Global（由 OpenRouter 路由）" : "中国" }
    var model: String {
        switch self {
        case .qwenApp: "qwen3.8-flash"
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
        let processStartedAt = ProcessInfo.processInfo.systemUptime
        do {
            let configuration = try BackendLifecycleConfiguration.resolve(
                environment: ProcessInfo.processInfo.environment
            )
            _model = State(initialValue: BetaChatModel(
                configuration: configuration,
                processStartedAt: processStartedAt
            ))
            _configurationError = State(initialValue: nil)
        } catch {
            _model = State(initialValue: nil)
            _configurationError = State(initialValue: "无法找到本机运行环境。请从仓库 scripts/run_beta_app.sh 启动。")
        }
    }

    var body: some Scene {
        Window("个人 AI 助理测试版", id: "main") {
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
    private var lastAssistantResponseInterrupted = false
    private let microphone = LocalMicrophoneCapture()
    private let speechPlayback = SpeechPlaybackController(engine: AVSpeechEngine())
    private var voiceTimerTask: Task<Void, Never>?
    private var voiceSenderTask: Task<Void, Never>?
    private var voiceReceiverTask: Task<Void, Never>?
    private var voiceFrameContinuation: AsyncStream<CapturedVoiceFrame>.Continuation?
    private var voiceStream: LocalVoiceStream?
    private var voiceFinalSegments: [String] = []
    private var voiceStreamFailed = false
    private var voiceStreamFailureMessage: String?
    private var voiceFrameReadyAt: [UInt32: TimeInterval] = [:]
    private var partialLatencySamples: [TimeInterval] = []
    private var stopToDraftSamples: [TimeInterval] = []
    private(set) var startupLatency: TimeInterval?
    private var voiceNextSequence: UInt32 = 0
    private let processStartedAt: TimeInterval
    private(set) var isStarting = false
    private(set) var startupFailed = false
    private(set) var performanceDiagnosticsEnabled =
        ProcessInfo.processInfo.environment["PAC_BETA_PERF_DIAGNOSTICS"] == "1"
    private let defaults = UserDefaults.standard
    private(set) var status = "正在连接本机服务…"
    private(set) var messages: [LocalChatMessage] = []
    private(set) var isRecordingVoice = false
    private(set) var isTranscribingVoice = false
    private(set) var voiceSeconds = 0
    private(set) var partialTranscript = ""
    var draft = ""
    var source: ModelSource {
        didSet {
            defaults.set(source.rawValue, forKey: "beta.model.source")
            if oldValue != source { modelSelectionDidChange() }
        }
    }
    var localModel: String {
        didSet {
            defaults.set(localModel, forKey: "beta.model.local")
            if oldValue != localModel { modelSelectionDidChange() }
        }
    }
    var cloudProvider: CloudProvider {
        didSet {
            defaults.set(cloudProvider.rawValue, forKey: "beta.model.cloud-provider")
            if oldValue != cloudProvider { modelSelectionDidChange() }
        }
    }

    var isStreaming: Bool { activeRequest != nil }
    var performanceSummary: String {
        guard performanceDiagnosticsEnabled else { return "" }
        let partial = Self.p95Milliseconds(partialLatencySamples)
        let final = Self.p95Milliseconds(stopToDraftSamples)
        return [
            "启动至本机服务就绪：\(startupLatency.map { Self.formatMilliseconds($0 * 1_000) } ?? "采集中") ms",
            "partial 帧就绪至 UI 更新：n=\(partialLatencySamples.count)，P95 \(partial.map(Self.formatMilliseconds) ?? "采集中") ms",
            "停止至 final 入草稿：n=\(stopToDraftSamples.count)，P95 \(final.map(Self.formatMilliseconds) ?? "采集中") ms",
        ].joined(separator: "\n")
    }
    var canStartVoiceCapture: Bool {
        client != nil && !isRecordingVoice && !isTranscribingVoice
    }
    var usesCloud: Bool { source == .cloud }
    var selectedProvider: String { usesCloud ? cloudProvider.rawValue : "ollama" }
    var selectedModel: String { usesCloud ? cloudProvider.model : localModel }
    var selectedRegion: String { usesCloud ? cloudProvider.region : "仅本机" }
    var selectedModelTitle: String { usesCloud ? cloudProvider.title : "Ollama 本地模型" }
    var latestAssistantText: String? {
        guard let message = messages.last, message.role == "assistant",
              !message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              activeRequest == nil,
              !lastAssistantResponseInterrupted
        else { return nil }
        return message.content
    }
    init(configuration: BackendLifecycleConfiguration, processStartedAt: TimeInterval) {
        self.processStartedAt = processStartedAt
        source = ModelSource(rawValue: defaults.string(forKey: "beta.model.source") ?? "local") ?? .local
        localModel = defaults.string(forKey: "beta.model.local") ?? "qwen3.5:0.8b"
        cloudProvider = CloudProvider(
            rawValue: defaults.string(forKey: "beta.model.cloud-provider") ?? "qwen-app"
        ) ?? .qwenApp
        supervisor = LocalBackendSupervisor(
            pythonExecutableURL: configuration.pythonExecutableURL,
            backendDirectoryURL: configuration.backendDirectoryURL
        )
    }

    func start() async {
        guard client == nil, !isStarting else { return }
        isStarting = true
        defer { isStarting = false }
        let backendSupervisor = supervisor
        do {
            let handshake = try await Task.detached { try backendSupervisor.start() }.value
            let localClient = try LocalAPIClient(baseURL: handshake.baseURL, token: handshake.token)
            guard try await localClient.health() else { throw LocalAPIClientError.invalidResponse }
            client = localClient
            startupFailed = false
            startupLatency = max(0, ProcessInfo.processInfo.systemUptime - processStartedAt)
            status = "本机服务已连接；当前模型：\(selectedProvider) / \(selectedModel)"
        } catch {
            await Task.detached { try? backendSupervisor.stop() }.value
            startupFailed = true
            if let supervisorError = error as? LocalBackendSupervisorError {
                switch supervisorError {
                case .backendRuntimeUnavailable:
                    status = "找不到本机 Python 或服务代码。请检查虚拟环境，再重试。"
                case .launchFailed:
                    status = "本机服务进程无法启动。请检查 Python 环境，再重试。"
                case .startupTimedOut:
                    status = "本机服务启动超时。请检查依赖和端口占用，再重试。"
                case .invalidHandshake:
                    status = "本机服务握手失败，未建立连接。请重试。"
                case .alreadyRunning:
                    status = "本机服务已在启动或运行。请稍候后重试。"
                case .shutdownTimedOut:
                    status = "上一次本机服务未能正常退出。请退出应用后重新启动。"
                }
            } else {
                status = "本机服务启动失败：\(error.localizedDescription)"
            }
        }
    }

    func send() {
        guard activeRequest == nil, !isRecordingVoice, !isTranscribingVoice, let client else { return }
        guard !selectedModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            status = "请先在模型设置中选择模型。"
            return
        }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        messages.append(LocalChatMessage(role: "user", content: text))
        messages.append(LocalChatMessage(role: "assistant", content: ""))
        var contextMessages = Array(messages.dropLast())
        if lastAssistantResponseInterrupted, contextMessages.last?.role == "assistant" {
            contextMessages.removeLast()
        }
        lastAssistantResponseInterrupted = false
        let context = nonemptyMessages(contextMessages)
        let provider = selectedProvider
        let modelID = selectedModel
        let confirmedForThisRequest = usesCloud
        let requestID = UUID()
        activeRequestID = requestID
        status = "正在使用\(usesCloud ? "云端" : "本地")模型生成：\(provider) / \(modelID)"
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
                self.status = "本机服务已连接；本轮使用：\(provider) / \(modelID)"
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
        let interrupted = activeRequest != nil
        activeRequest?.cancel()
        activeRequest = nil
        activeRequestID = nil
        if interrupted, messages.last?.role == "assistant" {
            lastAssistantResponseInterrupted = true
        }
        if usesCloud {
            status = "已停止接收回复；云端服务是否停止生成未知。"
        } else {
            status = "已停止接收回复；Ollama 可能仍在结束本机生成。"
        }
    }

    private func modelSelectionDidChange() {
        if activeRequest != nil {
            if messages.last?.role == "assistant" {
                lastAssistantResponseInterrupted = true
            }
            activeRequest?.cancel()
            activeRequest = nil
            activeRequestID = nil
        }
        guard client != nil else { return }
        status = "本机服务已连接；当前模型：\(selectedProvider) / \(selectedModel)"
    }

    func startVoiceCapture() async {
        guard let client, !isRecordingVoice, !isTranscribingVoice else { return }
        if activeRequest != nil { stop() }
        stopLocalSpeech()
        status = "正在连接本机实时识别…"
        do {
            let stream = try await connectVoiceStream(client)
            voiceStream = stream
            voiceFinalSegments = []
            partialTranscript = ""
            voiceStreamFailed = false
            voiceStreamFailureMessage = nil
            voiceFrameReadyAt.removeAll(keepingCapacity: true)
            voiceNextSequence = 0
            let (frames, continuation) = AsyncStream<CapturedVoiceFrame>.makeStream(bufferingPolicy: .bufferingOldest(6))
            voiceFrameContinuation = continuation
            voiceSenderTask = Task { [weak self] in
                do {
                    for await frame in frames {
                        guard let self else { return }
                        let expectedSequence = self.voiceNextSequence
                        if self.performanceDiagnosticsEnabled {
                            self.voiceFrameReadyAt[expectedSequence] = frame.readyAtUptime
                        }
                        let sentSequence = try await stream.sendFrame(frame.pcm16LE)
                        guard sentSequence == expectedSequence else {
                            throw LocalAPIClientError.invalidResponse
                        }
                        self.voiceNextSequence &+= 1
                    }
                } catch {
                    self?.voiceStreamFailed = true
                    self?.voiceStreamFailureMessage = error.localizedDescription
                }
            }
            voiceReceiverTask = Task { [weak self] in
                do {
                    while !Task.isCancelled {
                        let event = try await stream.receive()
                        await MainActor.run {
                            guard let self else { return }
                            if event.type == "partial" {
                                self.partialTranscript = event.text ?? ""
                                self.recordPartialVisible(sequence: event.sequence)
                            } else if event.type == "final", let text = event.text, !text.isEmpty {
                                self.voiceFinalSegments.append(text)
                                self.partialTranscript = ""
                            } else if event.type == "error" {
                                self.voiceStreamFailed = true
                                self.voiceStreamFailureMessage = event.message
                            }
                        }
                        if event.type == "ended" || event.type == "error" { break }
                    }
                } catch {
                    self?.voiceStreamFailed = true
                    self?.voiceStreamFailureMessage = error.localizedDescription
                }
            }
            try await microphone.start(onFrame: { frame in
                switch continuation.yield(frame) {
                case .enqueued: true
                case .dropped, .terminated: false
                @unknown default: false
                }
            })
            isRecordingVoice = true
            voiceSeconds = 0
            status = "本机实时识别中；音频仅发往本机，最长 30 秒。"
            voiceTimerTask?.cancel()
            voiceTimerTask = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                    guard let self, self.isRecordingVoice else { return }
                    self.voiceSeconds += 1
                    if self.voiceSeconds >= LocalMicrophoneCapture.maximumDurationSeconds {
                        await self.finishVoiceCapture()
                        return
                    }
                }
            }
        } catch {
            microphone.discard()
            cancelVoiceStream()
            status = error.localizedDescription
        }
    }

    private func connectVoiceStream(_ client: LocalAPIClient) async throws -> LocalVoiceStream {
        let attempts = 5
        var lastFailure: String?
        for attempt in 0..<attempts {
            let stream = try client.openVoiceStream()
            do {
                try await stream.start()
                let ready = try await stream.receive()
                if ready.type == "error", let message = ready.message {
                    throw LocalAPIClientError.voiceStreamRejected(message)
                }
                guard ready.type == "ready" else {
                    throw LocalAPIClientError.invalidResponse
                }
                return stream
            } catch let error as LocalAPIClientError {
                stream.cancel()
                if case .voiceStreamRejected = error { throw error }
                lastFailure = error.localizedDescription
                guard attempt + 1 < attempts else { break }
                status = "正在重试连接本机语音服务…（\(attempt + 2)/\(attempts)）"
                try await Task.sleep(nanoseconds: 200_000_000)
            } catch {
                stream.cancel()
                lastFailure = error.localizedDescription
                guard attempt + 1 < attempts else { break }
                status = "正在重试连接本机语音服务…（\(attempt + 2)/\(attempts)）"
                try await Task.sleep(nanoseconds: 200_000_000)
            }
        }
        throw LocalAPIClientError.voiceStreamUnavailable(reason: lastFailure)
    }

    func finishVoiceCapture(stopTappedAtUptime: TimeInterval? = nil) async {
        guard isRecordingVoice else { return }
        voiceTimerTask?.cancel()
        voiceTimerTask = nil
        isRecordingVoice = false
        isTranscribingVoice = true
        status = "正在完成本机实时识别…"
        do {
            try microphone.finishStreaming()
            voiceFrameContinuation?.finish()
            voiceFrameContinuation = nil
            await voiceSenderTask?.value
            try await voiceStream?.finish()
            await voiceReceiverTask?.value
            guard !voiceStreamFailed else { throw LocalAPIClientError.invalidResponse }
            let transcript = voiceFinalSegments.joined(separator: "")
            let existing = draft.trimmingCharacters(in: .whitespacesAndNewlines)
            if !transcript.isEmpty { draft = existing.isEmpty ? transcript : existing + "\n" + transcript }
            if performanceDiagnosticsEnabled, let stopTappedAtUptime, !transcript.isEmpty {
                stopToDraftSamples.append(max(0, ProcessInfo.processInfo.systemUptime - stopTappedAtUptime))
            }
            partialTranscript = ""
            status = transcript.isEmpty
                ? "本次录音未识别到语音；音频已丢弃，请重试。"
                : "本机识别完成；转写已放入输入框，请检查后发送。"
        } catch {
            microphone.discard()
            try? await voiceStream?.abort()
            let reason = voiceStreamFailureMessage ?? error.localizedDescription
            status = "本机实时识别中断：\(reason)；未完成的转写已丢弃，没有切换到云端。"
        }
        cancelVoiceStream()
        isTranscribingVoice = false
    }

    func cancelVoiceCapture() {
        guard isRecordingVoice else { return }
        voiceTimerTask?.cancel()
        voiceTimerTask = nil
        isRecordingVoice = false
        microphone.discard()
        cancelVoiceStream(sendAbort: true)
        partialTranscript = ""
        status = "录音已取消并丢弃。"
    }

    private func cancelVoiceStream(sendAbort: Bool = false) {
        voiceFrameContinuation?.finish()
        voiceFrameContinuation = nil
        voiceSenderTask?.cancel()
        voiceSenderTask = nil
        voiceReceiverTask?.cancel()
        voiceReceiverTask = nil
        if let stream = voiceStream {
            if sendAbort {
                Task {
                    try? await stream.abort()
                    stream.cancel()
                }
            } else {
                stream.cancel()
            }
        }
        voiceStream = nil
    }

    func speakLocally(_ text: String) {
        guard !speechPlayback.speak(text) else {
            status = "正在本机朗读回复。"
            return
        }
        status = "没有可朗读的回复。"
    }

    func stopLocalSpeech() {
        if speechPlayback.interrupt() {
            status = "已停止本机朗读。"
        }
    }

    private func nonemptyMessages(_ values: [LocalChatMessage]) -> [LocalChatMessage] {
        values.filter { $0.role != "assistant" || !$0.content.isEmpty }
    }

    func recordPartialVisible(sequence: UInt32?) {
        guard performanceDiagnosticsEnabled, let sequence,
              let readyAt = voiceFrameReadyAt.removeValue(forKey: sequence)
        else { return }
        partialLatencySamples.append(max(0, ProcessInfo.processInfo.systemUptime - readyAt))
    }

    private static func p95Milliseconds(_ samples: [TimeInterval]) -> Double? {
        guard !samples.isEmpty else { return nil }
        let sorted = samples.sorted()
        let index = min(sorted.count - 1, Int(ceil(Double(sorted.count) * 0.95)) - 1)
        return sorted[index] * 1_000
    }

    private static func formatMilliseconds(_ value: Double) -> String {
        String(format: "%.1f", value)
    }

    func shutdown() async {
        voiceTimerTask?.cancel()
        voiceTimerTask = nil
        isRecordingVoice = false
        microphone.discard()
        cancelVoiceStream()
        stopLocalSpeech()
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

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("个人 AI 助理").font(.title2.bold())
                    Text(model.status).font(.caption).foregroundStyle(.secondary)
                    if model.startupFailed {
                        Button(model.isStarting ? "正在重试…" : "重试连接") {
                            Task { await model.start() }
                        }
                        .disabled(model.isStarting)
                        .accessibilityIdentifier("retry-local-service-button")
                    }
                    Text(model.usesCloud
                        ? "云端：聊天内容发送至\(model.selectedModelTitle)（\(model.selectedRegion)）"
                        : "本地：聊天内容仅发送到本机模型")
                        .font(.caption).foregroundStyle(model.usesCloud ? .orange : .secondary)
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
                                    ? "当前选择了云端模型；发送的聊天内容会直接发往所选服务商。关闭窗口后对话不会保存。"
                                    : "文字只发送到本机 Ollama；关闭窗口后对话不会保存。")
                            )
                            .padding(.top, 80)
                        }
                        ForEach(Array(model.messages.enumerated()), id: \.offset) { index, message in
                            HStack(alignment: .top) {
                                if message.role == "assistant" {
                                    responseBubble(message.content)
                                    if index == model.messages.count - 1,
                                       model.latestAssistantText == message.content {
                                        VStack(spacing: 6) {
                                            Button {
                                                model.speakLocally(message.content)
                                            } label: {
                                                Image(systemName: "speaker.wave.2")
                                            }
                                            .accessibilityLabel("本机朗读回复")
                                            .accessibilityIdentifier("local-speech-play-button")
                                            .help("在本机朗读最新回复")
                                            Button {
                                                model.stopLocalSpeech()
                                            } label: {
                                                Image(systemName: "stop.fill")
                                            }
                                            .accessibilityLabel("停止本机朗读")
                                            .accessibilityIdentifier("local-speech-stop-button")
                                            .help("停止本机朗读")
                                        }
                                        .buttonStyle(.borderless)
                                    }
                                } else {
                                    Spacer(minLength: 80)
                                    userBubble(message.content)
                                }
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
                if model.isRecordingVoice {
                    VStack(spacing: 4) {
                        Text("本机录音 \(model.voiceSeconds)/30 秒")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("取消并丢弃") { model.cancelVoiceCapture() }
                                .accessibilityIdentifier("voice-cancel-button")
                            Button("停止并识别") {
                                let tappedAt = ProcessInfo.processInfo.systemUptime
                                Task { await model.finishVoiceCapture(stopTappedAtUptime: tappedAt) }
                            }
                            .accessibilityIdentifier("voice-stop-transcribe-button")
                        }
                    }
                } else if model.isTranscribingVoice {
                    ProgressView("本机识别…")
                        .controlSize(.small)
                } else {
                    Button {
                        Task { await model.startVoiceCapture() }
                    } label: {
                        Label(model.isStreaming ? "打断并语音输入" : "语音输入", systemImage: "mic")
                    }
                    .accessibilityIdentifier("voice-input-button")
                    .disabled(!model.canStartVoiceCapture)
                    .help("点击后开始本机实时识别；生成中点击可打断当前回复并开始语音输入")
                }
                if model.isRecordingVoice && !model.partialTranscript.isEmpty {
                    Text(model.partialTranscript)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .accessibilityIdentifier("voice-partial-transcript")
                }
                if model.isStreaming {
                    Button("停止", action: model.stop)
                        .keyboardShortcut(.cancelAction)
                } else {
                    Button("发送", action: requestSend)
                        .keyboardShortcut(.return, modifiers: .command)
                        .disabled(
                            model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                || model.isRecordingVoice
                                || model.isTranscribingVoice
                        )
                }
            }
            .padding()
            if model.performanceDiagnosticsEnabled {
                Text(model.performanceSummary)
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    .padding(.bottom, 6)
                    .accessibilityIdentifier("beta-performance-diagnostics")
            }
        }
        .sheet(isPresented: $showingSettings) {
            BetaModelSettingsView(model: model)
        }
    }

    private func requestSend() {
        model.send()
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
    @State private var hasConfiguredCredential = false
    @State private var isUpdatingCredential = false
    private let keychain = KeychainCredentialStore(
        service: "com.personal-ai-assistant.phase0.provider"
    )
    private let credentialManager = CredentialManagementService(
        service: "com.personal-ai-assistant.phase0.provider",
        authorizer: TouchIDAuthorizer()
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
                Text("PAC 本机服务和 Ollama 是两个独立进程。请先启动 Ollama，并确认已安装此模型；PAC 服务已连接不代表 Ollama 已运行。")
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
                        .disabled(apiKey.isEmpty || isUpdatingCredential)
                    if hasConfiguredCredential {
                        Button("删除已保存的 Key", role: .destructive) { deleteCredential() }
                            .disabled(isUpdatingCredential)
                    }
                    if !saveMessage.isEmpty {
                        Text(saveMessage).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if model.cloudProvider == .qwenApp {
                    Text("千问应用 API 使用按量计费 Key（sk-ws-），与 Token Plan 个人版 Key 分开。请新建应用 API Key；不要复用曾公开过的 Key。")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Text("选择云端模型即表示后续聊天内容会直接发送给所选服务商（\(model.cloudProvider.title)，\(model.cloudProvider.model)，\(model.cloudProvider.region)），发送时不再逐条弹窗。切回本地模型即可停止云端发送。Key 保存在 Keychain，不进入聊天或设置文件。")
                    .font(.callout).foregroundStyle(.secondary)
                Label("千问 Token Plan 个人版 Key（sk-sp-）仅能通过官方支持的编程/智能体工具扩展使用，不接入本自建应用；千问应用 API 使用独立 Keychain 项 qwen-app。", systemImage: "info.circle")
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
            hasConfiguredCredential = try keychain.contains(account: model.cloudProvider.account)
            keyStatus = hasConfiguredCredential
                ? "已保存（\(model.cloudProvider.account)）"
                : "未配置（\(model.cloudProvider.account)）"
        } catch {
            hasConfiguredCredential = false
            keyStatus = "无法读取 Keychain 状态"
        }
    }

    private func saveCredential() {
        if model.cloudProvider == .qwenApp && !apiKey.hasPrefix("sk-ws-") {
            saveMessage = "千问应用 API Key 应以 sk-ws- 开头；sk-sp- Token Plan Key 不用于本应用。"
            return
        }
        let secret = apiKey
        let account = model.cloudProvider.account
        isUpdatingCredential = true
        Task {
            do {
                try await credentialManager.save(secret, account: account)
                apiKey = ""
                saveMessage = "已通过设备认证并安全保存。"
            } catch {
                saveMessage = "未更改 Keychain：\(error.localizedDescription)"
            }
            isUpdatingCredential = false
            refreshKeyStatus()
        }
    }

    private func deleteCredential() {
        let account = model.cloudProvider.account
        isUpdatingCredential = true
        Task {
            do {
                try await credentialManager.delete(account: account)
                saveMessage = "已通过设备认证并删除 Key。"
            } catch {
                saveMessage = "未更改 Keychain：\(error.localizedDescription)"
            }
            isUpdatingCredential = false
            refreshKeyStatus()
        }
    }
}
