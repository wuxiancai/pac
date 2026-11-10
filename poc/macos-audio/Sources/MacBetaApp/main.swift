import MacAudioPOC
import Observation
import SwiftUI
import UniformTypeIdentifiers

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
    private(set) var latestRunID: String?
    private(set) var latestRunStatus: LocalChatRunStatus?
    private(set) var importedTextFiles: [LocalImportedTextFile] = []
    private(set) var isImportingFiles = false
    private(set) var usageRecords: [LocalUsageRecord] = []
    private(set) var usageStatus = "尚未读取本机用量。"
    private(set) var isLoadingUsage = false
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
    private(set) var conversationID: String?
    private(set) var tasks: [LocalTaskItem] = []
    private(set) var taskStatus = ""
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
        client != nil && !isRecordingVoice && !isTranscribingVoice && !isImportingFiles
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
            let databaseKey = try DatabaseKeychainStore().loadOrCreateKey()
            let handshake = try await Task.detached {
                try backendSupervisor.start(databaseKey: databaseKey)
            }.value
            let localClient = try LocalAPIClient(baseURL: handshake.baseURL, token: handshake.token)
            guard try await localClient.health() else { throw LocalAPIClientError.invalidResponse }
            let history = try await localClient.chatHistory()
            conversationID = history.conversationID
            messages = history.messages
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
                case .databaseKeyDeliveryFailed:
                    status = "本机加密数据密钥无法安全交给服务进程，未启动服务。"
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
        guard activeRequest == nil, !isRecordingVoice, !isTranscribingVoice,
              !isImportingFiles, let client else { return }
        if usesCloud && !importedTextFiles.isEmpty {
            status = "已选资料目前只允许发送到本机模型；切回本地模型后再提问。"
            return
        }
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
        let importedDocumentIDs = importedTextFiles.map(\.importID)
        let activeConversationID = conversationID
        let requestID = UUID()
        activeRequestID = requestID
        latestRunID = nil
        latestRunStatus = nil
        status = "正在使用\(usesCloud ? "云端" : "本地")模型生成：\(provider) / \(modelID)"
        activeRequest = Task { [weak self] in
            var runID: String?
            do {
                for try await item in client.streamChat(
                    messages: context,
                    provider: provider,
                    model: modelID,
                    confirmedForThisRequest: confirmedForThisRequest,
                    importedDocumentIDs: importedDocumentIDs,
                    conversationID: activeConversationID
                ) {
                    guard let self else { return }
                    guard self.activeRequestID == requestID else { return }
                    switch item {
                    case .runID(let identifier):
                        runID = identifier
                        self.latestRunID = identifier
                        self.latestRunStatus = .running
                    case .delta(let delta):
                        if !Task.isCancelled, let index = self.messages.indices.last {
                            self.messages[index] = LocalChatMessage(
                                role: "assistant", content: self.messages[index].content + delta
                            )
                        }
                    }
                }
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "本机服务已连接；本轮使用：\(provider) / \(modelID)"
                self.activeRequest = nil
                self.activeRequestID = nil
                if runID != nil { self.latestRunStatus = .completed }
                if let runID {
                    await self.refreshRunStatus(runID, client: client)
                }
                return
            } catch is CancellationError {
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "已停止本轮生成"
            } catch {
                guard let self, self.activeRequestID == requestID else { return }
                self.status = "模型请求失败：\(error.localizedDescription)"
                self.activeRequest = nil
                self.activeRequestID = nil
                self.latestRunStatus = nil
                if let runID {
                    await self.refreshRunStatus(runID, client: client)
                }
                return
            }
            guard let self, self.activeRequestID == requestID else { return }
            self.activeRequest = nil
            self.activeRequestID = nil
        }
    }

    func stop() {
        let interrupted = activeRequest != nil
        let stoppedRunID = latestRunID
        let runClient = client
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
        if let stoppedRunID, let runClient { watchStoppedRun(stoppedRunID, client: runClient) }
    }

    private func refreshRunStatus(_ runID: String, client: LocalAPIClient) async {
        guard let runStatus = try? await client.chatRunStatus(runID: runID),
              latestRunID == runID
        else { return }
        latestRunStatus = runStatus
    }

    private func watchStoppedRun(_ runID: String, client: LocalAPIClient) {
        latestRunStatus = nil
        Task { @MainActor [weak self] in
            for _ in 0..<8 {
                try? await Task.sleep(nanoseconds: 150_000_000)
                guard let self, self.latestRunID == runID else { return }
                guard let runStatus = try? await client.chatRunStatus(runID: runID) else {
                    continue
                }
                self.latestRunStatus = runStatus
                if runStatus != .running && runStatus != .created { return }
            }
        }
    }

    func importSelectedFiles(_ urls: [URL]) async {
        guard !isImportingFiles else {
            status = "正在添加本机资料，请稍候。"
            return
        }
        guard let client else { return }
        guard !urls.isEmpty else { return }
        if importedTextFiles.count + urls.count > 4 {
            status = "一次最多附加 4 个文本文件；请分批选择。"
            return
        }
        isImportingFiles = true
        defer { isImportingFiles = false }
        for url in urls {
            let suffix = url.pathExtension.lowercased()
            guard ["txt", "md", "markdown"].contains(suffix) else {
                status = "目前支持 TXT 和 Markdown 文件；PDF 导入待安全验证。"
                return
            }
            let accessed = url.startAccessingSecurityScopedResource()
            defer { if accessed { url.stopAccessingSecurityScopedResource() } }
            do {
                let values = try url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
                guard values.isRegularFile == true,
                      let fileSize = values.fileSize,
                      fileSize > 0,
                      fileSize <= 10 * 1024 * 1024
                else {
                    status = "文件必须是非空普通文件且不超过 10 MB。"
                    return
                }
                let handle = try FileHandle(forReadingFrom: url)
                defer { try? handle.close() }
                let data = try handle.read(upToCount: 10 * 1024 * 1024 + 1) ?? Data()
                guard data.count <= 10 * 1024 * 1024 else {
                    status = "文件超过 10 MB 上限。"
                    return
                }
                let imported = try await client.importSelectedText(
                    data: data,
                    fileName: url.lastPathComponent
                )
                importedTextFiles.append(imported)
                status = "已添加本机资料：\(imported.displayName)（\(imported.characterCount) 字符）"
            } catch {
                status = "无法添加文件：\(error.localizedDescription)"
                return
            }
        }
    }

    func removeImportedFile(_ file: LocalImportedTextFile) async {
        guard activeRequest == nil else {
            status = "请先停止当前生成，再移除资料。"
            return
        }
        guard let client else { return }
        do {
            try await client.removeImportedText(importID: file.importID)
            importedTextFiles.removeAll { $0.id == file.id }
            status = "已从本机临时资料中移除：\(file.displayName)"
        } catch {
            status = "无法从本机服务移除资料：\(error.localizedDescription)"
        }
    }

    func reportFileImportError(_ error: Error) {
        status = "无法打开所选文件：\(error.localizedDescription)"
    }

    func refreshTasks() async {
        guard let client else { return }
        do {
            tasks = try await client.listTasks()
            taskStatus = "本机任务 · 完成 30 天后自动清理"
        } catch {
            taskStatus = "无法读取本机任务：\(error.localizedDescription)"
        }
    }

    func addTask(title: String) async {
        guard let client else { return }
        do {
            _ = try await client.createTask(title: title)
            await refreshTasks()
        } catch {
            taskStatus = "无法保存本机任务：\(error.localizedDescription)"
        }
    }

    func deleteTask(_ task: LocalTaskItem) async {
        guard let client else { return }
        do {
            try await client.deleteTask(id: task.id)
            tasks.removeAll { $0.id == task.id }
            taskStatus = "已从本机数据库删除任务。"
        } catch {
            taskStatus = "无法删除本机任务：\(error.localizedDescription)"
        }
    }

    func updateTask(_ task: LocalTaskItem, status: String) async {
        guard let client else { return }
        do {
            _ = try await client.transitionTask(id: task.id, status: status)
            await refreshTasks()
        } catch {
            taskStatus = "无法更新任务状态：\(error.localizedDescription)"
        }
    }

    func deleteChatHistory() async {
        guard activeRequest == nil, let client else {
            status = "请先停止当前生成，再删除聊天记录。"
            return
        }
        do {
            try await client.deleteChatHistory()
            messages.removeAll()
            conversationID = nil
            lastAssistantResponseInterrupted = false
            let history = try await client.chatHistory()
            conversationID = history.conversationID
            status = "已从本机加密数据库删除聊天记录。"
        } catch {
            status = "无法删除本机聊天记录：\(error.localizedDescription)"
        }
    }

    func refreshUsage() async {
        guard let client, !isLoadingUsage else { return }
        isLoadingUsage = true
        defer { isLoadingUsage = false }
        do {
            let snapshot = try await client.recentUsage()
            usageRecords = snapshot.records
            usageStatus = snapshot.records.isEmpty
                ? "此进程尚无聊天用量记录。记录仅保存在本机内存，退出后清空。"
                : "显示最近 \(snapshot.records.count) 条记录；退出应用后记录清空。"
        } catch {
            usageStatus = "无法读取本机用量：\(error.localizedDescription)"
        }
    }

    private func modelSelectionDidChange() {
        if activeRequest != nil {
            let stoppedRunID = latestRunID
            let runClient = client
            if messages.last?.role == "assistant" {
                lastAssistantResponseInterrupted = true
            }
            activeRequest?.cancel()
            activeRequest = nil
            activeRequestID = nil
            if let stoppedRunID, let runClient { watchStoppedRun(stoppedRunID, client: runClient) }
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
        switch speechPlayback.speak(text) {
        case .started:
            status = "已开始本机朗读回复。"
        case .emptyText:
            status = "没有可朗读的回复。"
        case .existingSpeechCouldNotBeStopped:
            status = "无法停止上一段本机朗读；当前回复未排队。"
        }
    }

    func stopLocalSpeech() {
        if speechPlayback.interrupt() {
            status = "已停止本机朗读。"
        }
    }

    private func nonemptyMessages(_ values: [LocalChatMessage]) -> [LocalChatMessage] {
        Array(values.filter { $0.role != "assistant" || !$0.content.isEmpty }
            .suffix(LocalAPIClient.maximumChatMessages))
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
    @State private var showingFileImporter = false
    @State private var showingUsage = false
    @State private var showingDeleteChatConfirmation = false
    @State private var showingTasks = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("个人 AI 助理").font(.title2.bold())
                    Text(model.status).font(.caption).foregroundStyle(.secondary)
                    if let runID = model.latestRunID, let runStatus = model.latestRunStatus {
                        Text("本轮运行：\(runStatus.displayName)（\(runID.prefix(8))）")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .accessibilityIdentifier("chat-run-status")
                    }
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
                Button {
                    showingTasks = true
                    Task { await model.refreshTasks() }
                } label: {
                    Label("任务", systemImage: "checklist")
                }
                .accessibilityIdentifier("tasks-button")
                Button {
                    showingUsage = true
                    Task { await model.refreshUsage() }
                } label: {
                    Label("用量", systemImage: "chart.bar")
                }
                .accessibilityIdentifier("usage-button")
                if !model.messages.isEmpty {
                    Button(role: .destructive) {
                        showingDeleteChatConfirmation = true
                    } label: {
                        Label("删除对话", systemImage: "trash")
                    }
                    .disabled(model.isStreaming)
                    .accessibilityIdentifier("delete-chat-history-button")
                }
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
                                    ? "聊天记录加密保存在本机；本轮内容还会发送到所选云服务商。可随时手动删除。"
                                    : "聊天记录加密保存在本机；文字只发送到本机 Ollama。可随时手动删除。")
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
            if !model.importedTextFiles.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(model.importedTextFiles) { file in
                            HStack(spacing: 5) {
                                Label(file.displayName, systemImage: "doc.text")
                                Button {
                                    Task { await model.removeImportedFile(file) }
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                }
                                .buttonStyle(.plain)
                                .disabled(model.isStreaming)
                                .accessibilityLabel("移除资料 \(file.displayName)")
                            }
                            .font(.caption)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 5)
                            .background(.quaternary, in: Capsule())
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.top, 8)
            }
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
                        showingFileImporter = true
                    } label: {
                        Label("添加资料", systemImage: "paperclip")
                    }
                    .disabled(model.isImportingFiles || model.isRecordingVoice || model.isTranscribingVoice)
                    .help("选择 TXT 或 Markdown 文件；资料只用于本机模型，PDF 导入尚未启用")
                    .accessibilityIdentifier("import-text-file-button")
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
                                || model.isImportingFiles
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
        .confirmationDialog(
            "删除本机聊天记录？",
            isPresented: $showingDeleteChatConfirmation,
            titleVisibility: .visible
        ) {
            Button("删除聊天记录", role: .destructive) {
                Task { await model.deleteChatHistory() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("此操作会从本机加密数据库永久删除当前对话及其消息。")
        }
        .sheet(isPresented: $showingSettings) {
            BetaModelSettingsView(model: model)
        }
        .sheet(isPresented: $showingTasks) {
            TaskBoardView(model: model)
                .frame(minWidth: 480, minHeight: 420)
        }
        .sheet(isPresented: $showingUsage) {
            UsageHistoryView(model: model)
                .frame(minWidth: 520, minHeight: 420)
        }
        .fileImporter(
            isPresented: $showingFileImporter,
            allowedContentTypes: [
                .plainText,
                UTType(filenameExtension: "md") ?? .plainText,
                UTType(filenameExtension: "markdown") ?? .plainText,
            ],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                Task { await model.importSelectedFiles(urls) }
            case .failure(let error):
                model.reportFileImportError(error)
            }
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
private struct UsageHistoryView: View {
    @Bindable var model: BetaChatModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("本机用量").font(.title2.bold())
                Spacer()
                Button("刷新") { Task { await model.refreshUsage() } }
                    .disabled(model.isLoadingUsage)
            }
            Text(model.usageStatus).font(.caption).foregroundStyle(.secondary)
            Text("token 与费用只显示服务端实际返回值；未知时保留为空，不进行估算。")
                .font(.caption).foregroundStyle(.secondary)
            Divider()
            if model.usageRecords.isEmpty {
                ContentUnavailableView("暂无记录", systemImage: "chart.bar", description: Text(model.usageStatus))
            } else {
                List(model.usageRecords) { record in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text("\(record.provider) / \(record.model)").font(.headline)
                            Spacer()
                            Text("\(record.latencyMS) ms").monospacedDigit()
                        }
                        HStack {
                            Text("\(record.purposeDisplayName) · \(record.dataLevelDisplayName)")
                            Spacer()
                            Text(record.status.displayName)
                        }
                        HStack {
                            Text("\(record.regionDisplayName) · \(record.startedAtDate.formatted(date: .numeric, time: .shortened))")
                            Spacer()
                            Text("\(record.usageState == "actual" ? "实际 token" : record.usageState == "estimated" ? "估算 token" : "token 未知")")
                        }
                        HStack {
                            Text("输入 \(record.promptTokens.map { String($0) } ?? "—")（缓存命中 \(record.cachedPromptTokens.map { String($0) } ?? "—")）/ 输出 \(record.completionTokens.map { String($0) } ?? "—")")
                            Spacer()
                            Text(costDescription(record))
                        }
                    }
                    .font(.caption)
                    .padding(.vertical, 3)
                }
                .listStyle(.plain)
            }
        }
        .padding()
        .task { await model.refreshUsage() }
    }

    private func costDescription(_ record: LocalUsageRecord) -> String {
        guard let amount = record.costAmount, let currency = record.costCurrency else {
            return "费用未知"
        }
        let kind = record.costState == "actual" ? "实扣" : "估算"
        return "\(kind) \(amount.formatted()) \(currency)"
    }
}

@available(macOS 14.0, *)
private struct TaskBoardView: View {
    @Bindable var model: BetaChatModel
    @State private var title = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("本机任务").font(.title2.bold())
            Text(model.taskStatus).font(.caption).foregroundStyle(.secondary)
            HStack {
                TextField("新任务标题", text: $title)
                    .textFieldStyle(.roundedBorder)
                Button("添加") {
                    let value = title.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !value.isEmpty else { return }
                    title = ""
                    Task { await model.addTask(title: value) }
                }
                .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            List(model.tasks) { task in
                HStack {
                    VStack(alignment: .leading) {
                        Text(task.title)
                        Text(task.status).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if task.status == "PENDING" || task.status == "PAUSED" || task.status == "FAILED" {
                        Button("准备") { Task { await model.updateTask(task, status: "READY") } }
                    } else if task.status == "READY" {
                        Button("开始") { Task { await model.updateTask(task, status: "RUNNING") } }
                    } else if task.status == "RUNNING" || task.status == "PARTIAL" {
                        Button("完成") { Task { await model.updateTask(task, status: "COMPLETED") } }
                    }
                    Button(role: .destructive) {
                        Task { await model.deleteTask(task) }
                    } label: {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("删除任务：\(task.title)")
                }
            }
            HStack {
                Button("刷新") { Task { await model.refreshTasks() } }
                Spacer()
                Text("任务保存在本机；完成 30 天后自动删除。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
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
