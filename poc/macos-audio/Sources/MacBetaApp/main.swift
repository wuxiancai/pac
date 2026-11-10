import MacAudioPOC
import AppKit
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
    private(set) var hasOlderMessages = false
    private(set) var isLoadingOlderMessages = false
    private(set) var conversationID: String?
    private(set) var pendingSourceMessageID: String?
    private(set) var conversations: [LocalConversationItem] = []
    private(set) var tasks: [LocalTaskItem] = []
    private(set) var memories: [LocalMemoryItem] = []
    private(set) var memoryStatus = ""
    private(set) var memoryVersions: [LocalMemoryVersion] = []
    private(set) var memorySource: LocalMemorySource?
    private(set) var taskStatus = ""
    private(set) var taskNotificationStatus = "通知默认关闭。"
    private(set) var backupStatus = "备份口令仅用于本次导出，不会保存。"
    private let taskReminderManager = TaskReminderManager.shared
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
    var assistantKey: String {
        didSet { defaults.set(assistantKey, forKey: "beta.assistant.key") }
    }
    let assistantProfiles: [(key: String, title: String)] = [
        ("main_assistant", "总助理"),
        ("project_assistant", "项目助理"),
        ("meeting_assistant", "会议助理"),
        ("task_planner", "任务规划"),
    ]
    var selectedAssistantTitle: String {
        assistantProfiles.first(where: { $0.key == assistantKey })?.title ?? "总助理"
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
        let savedAssistant = defaults.string(forKey: "beta.assistant.key") ?? "main_assistant"
        assistantKey = ["main_assistant", "project_assistant", "meeting_assistant", "task_planner"].contains(savedAssistant)
            ? savedAssistant : "main_assistant"
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
            hasOlderMessages = history.hasMore
            conversations = try await localClient.conversations()
            client = localClient
            if taskReminderManager.isEnabled {
                do {
                    tasks = try await localClient.listTasks()
                    await taskReminderManager.reconcile(tasks: tasks)
                } catch {
                    taskNotificationStatus = "无法重建任务提醒：\(error.localizedDescription)"
                }
            }
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
        let selectedAssistantKey = assistantKey
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
                    conversationID: activeConversationID,
                    assistantKey: selectedAssistantKey
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
                if let history = try? await client.chatHistory(conversationID: activeConversationID) {
                    self.messages = history.messages
                    self.hasOlderMessages = history.hasMore
                }
                await self.refreshConversations()
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

    var selectedConversationTitle: String {
        conversations.first(where: { $0.id == conversationID })?.title ?? "新对话"
    }

    func refreshConversations() async {
        guard let client else { return }
        do {
            conversations = try await client.conversations()
        } catch {
            status = "无法读取本机会话列表：\(error.localizedDescription)"
        }
    }

    func loadOlderMessages() async {
        guard !isLoadingOlderMessages, hasOlderMessages,
              let client, let conversationID, let cursor = messages.first?.id else { return }
        isLoadingOlderMessages = true
        defer { isLoadingOlderMessages = false }
        do {
            let page = try await client.chatHistory(
                conversationID: conversationID, beforeMessageID: cursor
            )
            guard page.conversationID == conversationID else { return }
            messages = page.messages + messages
            hasOlderMessages = page.hasMore
        } catch {
            status = "无法加载更早的聊天记录：\(error.localizedDescription)"
        }
    }

    func selectConversation(_ conversation: LocalConversationItem) async {
        guard activeRequest == nil, let client else {
            status = "请先停止当前生成，再切换会话。"
            return
        }
        do {
            let history = try await client.chatHistory(conversationID: conversation.id)
            conversationID = history.conversationID
            messages = history.messages
            hasOlderMessages = history.hasMore
            lastAssistantResponseInterrupted = false
            status = "已切换到：\(conversation.title)"
        } catch {
            status = "无法打开该会话：\(error.localizedDescription)"
        }
    }

    func openMemorySourceInChat(_ source: LocalMemorySource) async {
        guard activeRequest == nil, let client else {
            status = "请先停止当前生成，再打开来源会话。"
            return
        }
        do {
            var history = try await client.chatHistory(conversationID: source.conversationID)
            var loadedMessages = history.messages
            while !loadedMessages.contains(where: { $0.id == source.messageID }),
                  history.hasMore,
                  let cursor = loadedMessages.first?.id {
                history = try await client.chatHistory(
                    conversationID: source.conversationID, beforeMessageID: cursor
                )
                loadedMessages = history.messages + loadedMessages
            }
            guard loadedMessages.contains(where: { $0.id == source.messageID }) else {
                status = "来源消息已不在会话历史中。"
                return
            }
            conversationID = history.conversationID
            messages = loadedMessages
            hasOlderMessages = history.hasMore
            lastAssistantResponseInterrupted = false
            pendingSourceMessageID = source.messageID
            status = "已打开记忆来源会话：\(source.conversationTitle)"
        } catch {
            status = "无法打开记忆来源会话：\(error.localizedDescription)"
        }
    }

    func clearPendingSourceNavigation() {
        pendingSourceMessageID = nil
    }

    func renameConversation(_ conversation: LocalConversationItem, title: String) async {
        guard let client else { return }
        do {
            let renamed = try await client.renameConversation(id: conversation.id, title: title)
            conversations = conversations.map { $0.id == renamed.id ? renamed : $0 }
            status = "会话已重命名为：\(renamed.title)"
        } catch {
            status = "无法重命名会话：\(error.localizedDescription)"
        }
    }

    func createConversation() async {
        guard activeRequest == nil, let client else {
            status = "请先停止当前生成，再新建会话。"
            return
        }
        do {
            let conversation = try await client.createConversation()
            conversations.insert(conversation, at: 0)
            conversationID = conversation.id
            messages = []
            hasOlderMessages = false
            lastAssistantResponseInterrupted = false
            status = "已创建新会话。"
        } catch {
            status = "无法创建新会话：\(error.localizedDescription)"
        }
    }

    func refreshMemories() async {
        guard let client else { return }
        do {
            memories = try await client.listMemories()
            memoryStatus = "\(memories.count) 条用户确认记忆 · 仅保存在本机"
        } catch {
            memoryStatus = "无法读取本机记忆：\(error.localizedDescription)"
        }
    }

    func exportEncryptedBackup(to url: URL, password: String, replaceExisting: Bool) async {
        guard let client else { backupStatus = "本机服务尚未就绪。"; return }
        do {
            let bytes = try await client.exportEncryptedBackup(
                destinationPath: url.path, password: password, replaceExisting: replaceExisting
            )
            backupStatus = "已创建加密备份（\(ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file))）。"
        } catch {
            backupStatus = "备份失败：\(error.localizedDescription)"
        }
    }

    func restoreEncryptedBackup(from url: URL, password: String) async {
        do {
            try await TouchIDAuthorizer().authorize(reason: "恢复本机加密数据")
            guard let client else { backupStatus = "本机服务尚未就绪。"; return }
            let prebackupPath = try await client.restoreEncryptedBackup(sourcePath: url.path, password: password)
            backupStatus = "恢复完成。恢复前数据已保存在本机预备份：\(URL(fileURLWithPath: prebackupPath).lastPathComponent)"
            await refreshConversations()
            if let selected = conversations.first(where: { $0.id == conversationID }) ?? conversations.first {
                await selectConversation(selected)
            } else {
                messages = []
                conversationID = nil
                hasOlderMessages = false
            }
            await refreshTasks()
            await refreshMemories()
        } catch {
            backupStatus = "恢复失败：\(error.localizedDescription)"
        }
    }

    func refreshMemoryVersions(id: String) async {
        guard let client else { return }
        do {
            memoryVersions = try await client.memoryVersions(id: id)
            memoryStatus = "已加载 \(memoryVersions.count) 个记忆版本。"
        } catch {
            memoryVersions = []
            memoryStatus = "无法读取记忆版本：\(error.localizedDescription)"
        }
    }

    func refreshMemorySource(id: String) async {
        guard let client else { return }
        do {
            memorySource = try await client.memorySource(id: id)
        } catch {
            memorySource = nil
            memoryStatus = "无法读取记忆来源：\(error.localizedDescription)"
        }
    }

    func saveConfirmedMemory(
        subject: String, content: String, category: String, sourceMessageID: String? = nil,
        editingID: String? = nil
    ) async {
        guard let client else { return }
        do {
            if let editingID {
                _ = try await client.updateConfirmedMemory(
                    id: editingID, subject: subject, content: content, category: category
                )
            } else {
                _ = try await client.createConfirmedMemory(
                    subject: subject, content: content, category: category,
                    sourceMessageID: sourceMessageID
                )
            }
            memoryStatus = editingID == nil ? "已保存并确认记忆。" : "已确认修正并保存新版本。"
            await refreshMemories()
        } catch {
            memoryStatus = "无法保存已确认记忆：\(error.localizedDescription)"
        }
    }

    func deleteMemory(_ memory: LocalMemoryItem) async {
        guard let client else { return }
        do {
            try await client.deleteMemory(id: memory.id)
            memories.removeAll { $0.id == memory.id }
            memoryStatus = "已永久删除该记忆。"
        } catch {
            memoryStatus = "无法删除记忆：\(error.localizedDescription)"
        }
    }

    func refreshTasks() async {
        guard let client else { return }
        do {
            tasks = try await client.listTasks()
            await taskReminderManager.reconcile(tasks: tasks)
            taskStatus = "本机任务 · 完成 30 天后自动清理"
            taskNotificationStatus = taskReminderManager.isEnabled
                ? "本机任务提醒已启用。"
                : "通知默认关闭。"
        } catch {
            taskStatus = "无法读取本机任务：\(error.localizedDescription)"
        }
    }

    func addTask(title: String, reminderDate: Date?) async {
        guard let client else { return }
        do {
            let scheduleAt: String? = reminderDate.map {
                let formatter = ISO8601DateFormatter()
                formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                return formatter.string(from: $0)
            }
            let task = try await client.createTask(title: title, scheduleAt: scheduleAt)
            await taskReminderManager.schedule(task: task)
            await refreshTasks()
        } catch {
            taskStatus = "无法保存本机任务：\(error.localizedDescription)"
        }
    }

    func enableTaskNotifications() async {
        do {
            let granted = try await taskReminderManager.requestAndEnable()
            taskNotificationStatus = granted
                ? "已允许系统通知；本机任务提醒已开启。"
                : "系统未授权通知；任务仍保存在本机。"
            if granted { await taskReminderManager.reconcile(tasks: tasks) }
        } catch {
            taskNotificationStatus = "无法启用系统通知：\(error.localizedDescription)"
        }
    }

    func disableTaskNotifications() async {
        await taskReminderManager.disable()
        taskNotificationStatus = "本机任务提醒已关闭。"
    }

    func deleteTask(_ task: LocalTaskItem) async {
        guard let client else { return }
        do {
            try await client.deleteTask(id: task.id)
            taskReminderManager.remove(taskID: task.id)
            tasks.removeAll { $0.id == task.id }
            taskStatus = "已从本机数据库删除任务。"
        } catch {
            taskStatus = "无法删除本机任务：\(error.localizedDescription)"
        }
    }

    func updateTask(_ task: LocalTaskItem, status: String) async {
        guard let client else { return }
        do {
            let updated = try await client.transitionTask(id: task.id, status: status)
            if ["COMPLETED", "CANCELLED"].contains(updated.status) {
                taskReminderManager.remove(taskID: updated.id)
            }
            await taskReminderManager.schedule(task: updated)
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
            guard let conversationID else { return }
            try await client.deleteChatHistory(conversationID: conversationID)
            messages.removeAll()
            lastAssistantResponseInterrupted = false
            conversations.removeAll { $0.id == conversationID }
            if let remaining = conversations.first {
                await selectConversation(remaining)
            } else {
                await createConversation()
            }
            status = "已从本机加密数据库删除该会话。"
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
    @State private var showingBackup = false
    @State private var showingCalendar = false
    @State private var showingDeleteChatConfirmation = false
    @State private var showingTasks = false
    @State private var showingMemories = false
    @State private var showingRenameConversation = false
    @State private var renameTitle = ""

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
                Menu {
                    ForEach(model.assistantProfiles, id: \.key) { profile in
                        Button {
                            model.assistantKey = profile.key
                        } label: {
                            if model.assistantKey == profile.key {
                                Label(profile.title, systemImage: "checkmark")
                            } else {
                                Text(profile.title)
                            }
                        }
                    }
                } label: {
                    Label(model.selectedAssistantTitle, systemImage: "person.crop.circle")
                }
                .disabled(model.isStreaming)
                .accessibilityIdentifier("assistant-profile-menu")
                Menu {
                    ForEach(model.conversations) { conversation in
                        Button {
                            Task { await model.selectConversation(conversation) }
                        } label: {
                            if conversation.id == model.conversationID {
                                Label(conversation.title, systemImage: "checkmark")
                            } else {
                                Text(conversation.title)
                            }
                        }
                    }
                } label: {
                    Label(model.selectedConversationTitle, systemImage: "bubble.left.and.bubble.right")
                }
                .accessibilityIdentifier("conversation-picker-menu")
                Button {
                    renameTitle = model.selectedConversationTitle
                    showingRenameConversation = true
                } label: {
                    Label("重命名会话", systemImage: "pencil")
                }
                .disabled(model.conversationID == nil || model.isStreaming)
                .accessibilityIdentifier("rename-conversation-button")
                Button {
                    Task { await model.createConversation() }
                } label: {
                    Label("新对话", systemImage: "plus.bubble")
                }
                .disabled(model.isStreaming)
                .accessibilityIdentifier("new-conversation-button")
                Button {
                    showingMemories = true
                    Task { await model.refreshMemories() }
                } label: {
                    Label("记忆", systemImage: "brain.head.profile")
                }
                .accessibilityIdentifier("memories-button")
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
                Button { showingBackup = true } label: {
                    Label("备份", systemImage: "externaldrive.badge.plus")
                }
                .accessibilityIdentifier("backup-export-button")
                Button { showingCalendar = true } label: {
                    Label("日历", systemImage: "calendar")
                }
                .accessibilityIdentifier("calendar-read-only-button")
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
                        if model.hasOlderMessages {
                            Button {
                                let anchorID = model.messages.first?.id
                                Task {
                                    await model.loadOlderMessages()
                                    if let anchorID { proxy.scrollTo(anchorID, anchor: .top) }
                                }
                            } label: {
                                if model.isLoadingOlderMessages {
                                    ProgressView("正在加载更早记录…")
                                } else {
                                    Text("加载更早的聊天记录")
                                }
                            }
                            .disabled(model.isLoadingOlderMessages)
                            .frame(maxWidth: .infinity)
                            .accessibilityIdentifier("load-older-messages-button")
                        }
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
                            .id(message.id ?? "transient-\(index)")
                        }
                    }
                    .padding()
                }
                .onChange(of: model.messages.last?.content) { _, _ in
                    guard !model.messages.isEmpty else { return }
                    proxy.scrollTo(model.messages.count - 1, anchor: .bottom)
                }
                .onChange(of: model.pendingSourceMessageID) { _, messageID in
                    guard let messageID else { return }
                    proxy.scrollTo(messageID, anchor: .center)
                    model.clearPendingSourceNavigation()
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
        .sheet(isPresented: $showingMemories) {
            ConfirmedMemoryView(model: model)
                .frame(minWidth: 520, minHeight: 520)
        }
        .sheet(isPresented: $showingTasks) {
            TaskBoardView(model: model)
                .frame(minWidth: 480, minHeight: 420)
        }
        .sheet(isPresented: $showingUsage) {
            UsageHistoryView(model: model)
                .frame(minWidth: 520, minHeight: 420)
        }
        .sheet(isPresented: $showingBackup) {
            BackupExportView(model: model)
                .frame(minWidth: 440, minHeight: 300)
        }
        .sheet(isPresented: $showingCalendar) {
            CalendarReadOnlyView()
                .frame(minWidth: 520, minHeight: 420)
        }
        .alert("重命名当前会话", isPresented: $showingRenameConversation) {
            TextField("会话名称", text: $renameTitle)
            Button("取消", role: .cancel) {}
            Button("保存") {
                guard let conversation = model.conversations.first(where: { $0.id == model.conversationID }) else { return }
                Task { await model.renameConversation(conversation, title: renameTitle) }
            }
        } message: {
            Text("会话名称仅保存在本机。")
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
private struct BackupExportView: View {
    @Bindable var model: BetaChatModel
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var isExporting = false
    @State private var selectedBackup: URL?
    @State private var showingRestoreConfirmation = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("创建加密备份").font(.title2.bold())
            Text("选择保存位置后输入本份备份的独立口令。口令不会保存；恢复时需再次输入。")
                .foregroundStyle(.secondary)
            SecureField("备份口令", text: $password)
                .textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("backup-password-field")
            Text(model.backupStatus).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("选择备份文件…") { chooseBackup() }
                Text(selectedBackup?.lastPathComponent ?? "尚未选择备份")
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
                Button(isExporting ? "处理中…" : "恢复此备份") { showingRestoreConfirmation = true }
                    .disabled(password.isEmpty || selectedBackup == nil || isExporting || model.isStreaming)
                    .accessibilityIdentifier("backup-restore-confirm-button")
            }
            HStack {
                Button("完成") { dismiss() }
                Spacer()
                Button(isExporting ? "正在备份…" : "选择位置并加密备份") { chooseDestination() }
                    .disabled(password.isEmpty || isExporting)
                    .keyboardShortcut(.defaultAction)
                    .accessibilityIdentifier("backup-export-confirm-button")
            }
        }
        .padding(22)
        .alert("恢复加密备份？", isPresented: $showingRestoreConfirmation) {
            Button("取消", role: .cancel) {}
            Button("认证并恢复", role: .destructive) { restoreSelectedBackup() }
        } message: {
            Text("将先在本机创建当前数据的预备份，再替换聊天、任务和已确认记忆。此 Mac 的系统认证和备份口令都会验证。")
        }
    }

    private func chooseDestination() {
        let panel = NSSavePanel()
        panel.title = "保存加密备份"
        panel.nameFieldStringValue = "PersonalAssistant.pacbackup"
        panel.allowedContentTypes = [UTType(filenameExtension: "pacbackup") ?? .data]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let replaceExisting = FileManager.default.fileExists(atPath: url.path)
        let secret = password
        password = ""
        isExporting = true
        Task {
            await model.exportEncryptedBackup(to: url, password: secret, replaceExisting: replaceExisting)
            isExporting = false
        }
    }

    private func chooseBackup() {
        let panel = NSOpenPanel()
        panel.title = "选择加密备份"
        panel.allowedContentTypes = [UTType(filenameExtension: "pacbackup") ?? .data]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK else { return }
        selectedBackup = panel.url
    }

    private func restoreSelectedBackup() {
        guard let selectedBackup else { return }
        let secret = password
        password = ""
        isExporting = true
        Task {
            await model.restoreEncryptedBackup(from: selectedBackup, password: secret)
            isExporting = false
        }
    }
}

@available(macOS 14.0, *)
private struct CalendarReadOnlyView: View {
    @State private var service = CalendarReadOnlyService()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("本机日历（只读）").font(.title2.bold())
            Text("系统需要授予日历完整访问权限才能读取；应用只查询未来 30 天的事件，不会创建、修改或删除事件，也不会保存或发送日历内容。")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Text(service.status).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button(service.isLoading ? "正在读取…" : "授权并读取") {
                    Task { await service.loadUpcomingEvents() }
                }
                .disabled(service.isLoading)
                .accessibilityIdentifier("calendar-read-only-load-button")
            }
            List(service.events) { event in
                VStack(alignment: .leading, spacing: 4) {
                    Text(event.title).font(.body.weight(.medium))
                    HStack {
                        Text(event.isAllDay ? event.startDate.formatted(date: .abbreviated, time: .omitted) : event.startDate.formatted(date: .abbreviated, time: .shortened))
                        if !event.isAllDay {
                            Text("– \(event.endDate.formatted(date: .omitted, time: .shortened))")
                        }
                        Text("· \(event.calendarTitle)")
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
            }
            HStack {
                Spacer()
                Button("完成") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(18)
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
private struct ConfirmedMemoryView: View {
    @Bindable var model: BetaChatModel
    @State private var subject = ""
    @State private var content = ""
    @State private var category = "fact"
    @State private var editingID: String?
    @State private var sourceMessageID = ""
    @State private var historyMemory: LocalMemoryItem?
    @State private var sourceMemory: LocalMemoryItem?
    private let categories = ["fact", "preference", "goal", "event", "decision", "commitment", "relationship", "project"]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("已确认记忆").font(.title2.bold())
            Text("仅保存你在此处明确确认的内容；不会自动从对话提取。")
                .font(.caption).foregroundStyle(.secondary)
            Text(model.memoryStatus).font(.caption).foregroundStyle(.secondary)
            TextField("主题", text: $subject).textFieldStyle(.roundedBorder)
            Picker("类别", selection: $category) {
                ForEach(categories, id: \.self) { Text($0).tag($0) }
            }
            if editingID == nil {
                Picker("来源消息（当前会话）", selection: $sourceMessageID) {
                    Text("不关联聊天消息").tag("")
                    ForEach(model.messages.filter { $0.id != nil }, id: \.id) { message in
                        Text("\(message.role == "user" ? "我" : "助理")：\(message.content.prefix(70))")
                            .tag(message.id ?? "")
                    }
                }
            } else if !sourceMessageID.isEmpty {
                Text("来源消息 ID：\(sourceMessageID)").font(.caption).foregroundStyle(.secondary)
            }
            TextEditor(text: $content)
                .frame(minHeight: 90)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(.quaternary))
            HStack {
            Button(editingID == nil ? "确认并保存这条记忆" : "确认修正并保存新版本") {
                let cleanSubject = subject.trimmingCharacters(in: .whitespacesAndNewlines)
                let cleanContent = content.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !cleanSubject.isEmpty, !cleanContent.isEmpty else { return }
                let memoryID = editingID
                let sourceID = sourceMessageID.isEmpty ? nil : sourceMessageID
                Task {
                    await model.saveConfirmedMemory(
                        subject: cleanSubject, content: cleanContent, category: category,
                        sourceMessageID: sourceID, editingID: memoryID
                    )
                }
                subject = ""
                content = ""
                editingID = nil
                sourceMessageID = ""
            }
            .disabled(subject.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            if editingID != nil {
                Button("取消修正") {
                    editingID = nil
                    subject = ""
                    content = ""
                    sourceMessageID = ""
                }
            }
            }
            List(model.memories) { memory in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(memory.subject).font(.headline)
                        Spacer()
                        Button("编辑") {
                            editingID = memory.id
                            subject = memory.subject
                            content = memory.content
                            category = memory.category
                            sourceMessageID = memory.sourceMessageID ?? ""
                        }
                        .buttonStyle(.borderless)
                        Button("版本历史") {
                            historyMemory = memory
                            Task { await model.refreshMemoryVersions(id: memory.id) }
                        }
                        .buttonStyle(.borderless)
                        if memory.sourceMessageID != nil {
                            Button("查看来源") {
                                sourceMemory = memory
                                Task { await model.refreshMemorySource(id: memory.id) }
                            }
                            .buttonStyle(.borderless)
                        }
                        Button(role: .destructive) {
                            Task { await model.deleteMemory(memory) }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("删除记忆：\(memory.subject)")
                    }
                    Text(memory.content).font(.body)
                    Text("\(memory.category) · 用户确认").font(.caption).foregroundStyle(.secondary)
                    if let sourceMessageID = memory.sourceMessageID {
                        Text("来源消息：\(sourceMessageID)").font(.caption2).foregroundStyle(.tertiary)
                    }
                }
            }
            HStack {
                Button("刷新") { Task { await model.refreshMemories() } }
                Spacer()
                Text("记忆保留至手动删除；Embedding 未启用。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding()
        .sheet(item: $historyMemory) { memory in
            NavigationStack {
                List(model.memoryVersions) { version in
                    VStack(alignment: .leading, spacing: 5) {
                        Text("版本 \(version.versionNo) · \(version.changeReason)").font(.headline)
                        Text(version.snapshot.subject).font(.subheadline)
                        Text(version.snapshot.content).font(.body)
                        Text("\(version.snapshot.category) · \(version.createdAt)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
                .navigationTitle("\(memory.subject) · 版本历史")
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("完成") { historyMemory = nil }
                    }
                }
            }
            .frame(minWidth: 480, minHeight: 360)
        }
        .sheet(item: $sourceMemory) { memory in
            NavigationStack {
                Group {
                    if let source = model.memorySource {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(source.conversationTitle).font(.headline)
                            Text(source.role == "user" ? "用户消息" : "助理回复")
                                .font(.caption).foregroundStyle(.secondary)
                            ScrollView { Text(source.content).frame(maxWidth: .infinity, alignment: .leading) }
                            Text(source.createdAt).font(.caption2).foregroundStyle(.tertiary)
                        }
                        .padding()
                    } else {
                        ContentUnavailableView("来源消息不可用", systemImage: "text.bubble")
                    }
                }
                .navigationTitle("\(memory.subject) · 来源")
                .toolbar {
                    ToolbarItem(placement: .secondaryAction) {
                        if let source = model.memorySource {
                            Button("在对话中查看") {
                                sourceMemory = nil
                                Task { await model.openMemorySourceInChat(source) }
                            }
                        }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("完成") { sourceMemory = nil }
                    }
                }
            }
            .frame(minWidth: 480, minHeight: 360)
        }
    }
}

@available(macOS 14.0, *)
private struct TaskBoardView: View {
    @Bindable var model: BetaChatModel

    private func statusTitle(_ status: String) -> String {
        switch status {
        case "READY": "准备"
        case "RUNNING": "开始执行"
        case "WAITING": "等待"
        case "PAUSED": "暂停"
        case "PARTIAL": "部分完成"
        case "COMPLETED": "完成"
        case "FAILED": "标记失败"
        case "CANCELLED": "取消"
        default: status
        }
    }
    @State private var title = ""
    @State private var reminderEnabled = false
    @State private var reminderDate = Date().addingTimeInterval(3_600)

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
                    Task {
                        await model.addTask(
                            title: value,
                            reminderDate: reminderEnabled ? reminderDate : nil
                        )
                    }
                }
                .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            Toggle("为新任务设置提醒", isOn: $reminderEnabled)
            if reminderEnabled {
                DatePicker("提醒时间", selection: $reminderDate, in: Date()..., displayedComponents: [.date, .hourAndMinute])
                    .datePickerStyle(.compact)
            }
            HStack {
                Text(model.taskNotificationStatus).font(.caption).foregroundStyle(.secondary)
                Spacer()
                if TaskReminderManager.shared.isEnabled {
                    Button("关闭系统提醒") { Task { await model.disableTaskNotifications() } }
                } else {
                    Button("启用系统提醒") { Task { await model.enableTaskNotifications() } }
                }
            }
            List(model.tasks) { task in
                HStack {
                    VStack(alignment: .leading) {
                        Text(task.title)
                        Text(task.scheduleAt.map { "\(task.status) · \($0)" } ?? task.status)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let transitions = task.allowedTransitions, !transitions.isEmpty {
                        Menu("更新状态") {
                            ForEach(transitions, id: \.self) { status in
                                Button(statusTitle(status)) {
                                    Task { await model.updateTask(task, status: status) }
                                }
                            }
                        }
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
