import Foundation

public enum LocalAPIClientError: Error, Equatable {
    case invalidEndpoint
    case invalidResponse
    case requestFailed(statusCode: Int)
    case voiceStreamUnavailable(reason: String?)
    case voiceStreamRejected(String)
}

extension LocalAPIClientError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case .invalidEndpoint:
            return "本机服务地址无效。"
        case .invalidResponse:
            return "本机服务返回了无效响应。"
        case .requestFailed(let statusCode):
            return "本机服务请求失败（HTTP \(statusCode)）。"
        case .voiceStreamUnavailable(let reason):
            let detail = reason.map { "（\($0)）" } ?? ""
            return "无法连接本机语音服务\(detail)，请重试；音频未发送到云端。"
        case .voiceStreamRejected(let message):
            return "本机语音服务拒绝了连接：\(message)"
        }
    }
}

public struct LocalChatMessage: Codable, Equatable, Sendable {
    public let id: String?
    public let role: String
    public let content: String

    public init(id: String? = nil, role: String, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }

    enum CodingKeys: String, CodingKey { case id, role, content }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id)
        role = try container.decode(String.self, forKey: .role)
        content = try container.decode(String.self, forKey: .content)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(role, forKey: .role)
        try container.encode(content, forKey: .content)
    }
}

public enum LocalChatRunStatus: String, Decodable, Sendable {
    case created
    case running
    case completed
    case failed
    case cancelled

    public var displayName: String {
        switch self {
        case .created: "已创建"
        case .running: "运行中"
        case .completed: "已完成"
        case .failed: "失败"
        case .cancelled: "已取消"
        }
    }
}

public enum LocalChatStreamItem: Sendable {
    case runID(String)
    case delta(String)
}

public struct LocalImportedTextFile: Decodable, Identifiable, Sendable {
    public let importID: String
    public let displayName: String
    public let byteCount: Int
    public let characterCount: Int

    public var id: String { importID }

    enum CodingKeys: String, CodingKey {
        case importID = "import_id"
        case displayName = "display_name"
        case byteCount = "byte_count"
        case characterCount = "character_count"
    }
}

public struct LocalConversationItem: Decodable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let createdAt: String
    public let updatedAt: String
    public let messageCount: Int

    enum CodingKeys: String, CodingKey {
        case id, title
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case messageCount = "message_count"
    }
}

private struct LocalConversationList: Decodable {
    let conversations: [LocalConversationItem]
}

public struct LocalMemoryItem: Decodable, Identifiable, Sendable {
    public let id: String
    public let category: String
    public let subject: String
    public let content: String
    public let claimType: String
    public let sourceMessageID: String?
    public let confirmedAt: String

    enum CodingKeys: String, CodingKey {
        case id, category, subject, content
        case claimType = "claim_type"
        case sourceMessageID = "source_message_id"
        case confirmedAt = "confirmed_at"
    }
}

private struct LocalMemoryList: Decodable {
    let memories: [LocalMemoryItem]
}

public struct LocalSkillItem: Decodable, Identifiable, Sendable {
    public let id: String
    public let skillKey: String
    public let name: String
    public let description: String
    public let version: String
    public let status: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, version, status
        case skillKey = "skill_key"
    }
}

private struct LocalSkillList: Decodable {
    let skills: [LocalSkillItem]
}

public struct LocalMemoryVersionSnapshot: Decodable, Sendable {
    public let subject: String
    public let content: String
    public let category: String
    public let confirmedAt: String

    enum CodingKeys: String, CodingKey {
        case subject, content, category
        case confirmedAt = "confirmed_at"
    }
}

public struct LocalMemoryVersion: Decodable, Identifiable, Sendable {
    public let id: String
    public let versionNo: Int
    public let snapshot: LocalMemoryVersionSnapshot
    public let changeReason: String
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, snapshot
        case versionNo = "version_no"
        case changeReason = "change_reason"
        case createdAt = "created_at"
    }
}

private struct LocalMemoryVersionList: Decodable {
    let versions: [LocalMemoryVersion]
}

public struct LocalMemorySource: Decodable, Sendable {
    public let messageID: String
    public let conversationID: String
    public let conversationTitle: String
    public let role: String
    public let content: String
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case role, content
        case messageID = "message_id"
        case conversationID = "conversation_id"
        case conversationTitle = "conversation_title"
        case createdAt = "created_at"
    }
}

private struct LocalMemorySourceResponse: Decodable {
    let source: LocalMemorySource?
}

private struct BackupExportResponse: Decodable {
    let created: Bool
    let bytesWritten: Int

    enum CodingKeys: String, CodingKey {
        case created
        case bytesWritten = "bytes_written"
    }
}

private struct BackupExportPayload: Encodable {
    let destinationPath: String
    let password: String
    let replaceExisting: Bool

    enum CodingKeys: String, CodingKey {
        case password
        case destinationPath = "destination_path"
        case replaceExisting = "replace_existing"
    }
}

private struct BackupRestorePayload: Encodable {
    let sourcePath: String
    let password: String

    enum CodingKeys: String, CodingKey {
        case password
        case sourcePath = "source_path"
    }
}

private struct BackupRestoreResponse: Decodable {
    let restored: Bool
    let prebackupPath: String

    enum CodingKeys: String, CodingKey {
        case restored
        case prebackupPath = "prebackup_path"
    }
}

public struct LocalTaskItem: Decodable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let description: String
    public let status: String
    public let priority: Int
    public let scheduleAt: String?
    public let startedAt: String?
    public let completedAt: String?
    public let allowedTransitions: [String]?

    enum CodingKeys: String, CodingKey {
        case id, title, description, status, priority
        case scheduleAt = "schedule_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case allowedTransitions = "allowed_transitions"
    }
}

public struct LocalTaskList: Decodable, Sendable {
    public let tasks: [LocalTaskItem]
}

public struct LocalChatHistory: Decodable, Sendable {
    public let conversationID: String?
    public let messages: [LocalChatMessage]
    public let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case conversationID = "conversation_id"
        case messages
        case hasMore = "has_more"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        conversationID = try container.decodeIfPresent(String.self, forKey: .conversationID)
        messages = try container.decode([LocalChatMessage].self, forKey: .messages)
        hasMore = try container.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false
    }
}

public struct LocalUsageRecord: Decodable, Identifiable, Sendable {
    public let runID: String
    public let provider: String
    public let model: String
    public let region: String
    public let purpose: String
    public let dataLevel: String
    public let status: LocalChatRunStatus
    public let startedAt: Double
    public let completedAt: Double
    public let latencyMS: Int
    public let promptTokens: Int?
    public let completionTokens: Int?
    public let cachedPromptTokens: Int?
    public let costAmount: Double?
    public let costCurrency: String?
    public let usageState: String
    public let costState: String

    public var id: String { runID }

    public var startedAtDate: Date { Date(timeIntervalSince1970: startedAt) }

    public var regionDisplayName: String {
        if !region.isEmpty { return region }
        return provider == "ollama" ? "本机" : "区域未知"
    }

    public var purposeDisplayName: String {
        switch purpose {
        case "beta-interactive-chat": "交互式聊天"
        case "chat": "聊天"
        case "": "本机处理"
        default: purpose
        }
    }

    public var dataLevelDisplayName: String { "数据等级 \(dataLevel)" }

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case provider, model, region, purpose, status
        case dataLevel = "data_level"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case latencyMS = "latency_ms"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case cachedPromptTokens = "cached_prompt_tokens"
        case costAmount = "cost_amount"
        case costCurrency = "cost_currency"
        case usageState = "usage_state"
        case costState = "cost_state"
    }
}

public struct LocalUsageSnapshot: Decodable, Sendable {
    public let records: [LocalUsageRecord]
    public let budget: LocalMonthlyCloudBudget?
}

public struct LocalMonthlyCloudBudget: Decodable, Sendable {
    public let month: String
    public let estimatedSpentCNY: Double
    public let warningThresholdCNY: Double
    public let limitCNY: Double
    public let isEstimate: Bool
    public let warningReached: Bool
    public let blocked: Bool

    enum CodingKeys: String, CodingKey {
        case month, blocked
        case estimatedSpentCNY = "estimated_spent_cny"
        case warningThresholdCNY = "warning_threshold_cny"
        case limitCNY = "limit_cny"
        case isEstimate = "is_estimate"
        case warningReached = "warning_reached"
    }
}

/// Minimal native client for the authenticated, loopback-only POC health endpoint.
@available(macOS 12.0, *)
public final class LocalAPIClient: @unchecked Sendable {
    public static let maximumChatMessages = 20
    private let baseURL: URL
    private let token: String
    private let session: URLSession

    public convenience init(baseURL: URL, token: String) throws {
        try self.init(baseURL: baseURL, token: token, sessionConfiguration: nil)
    }

    init(
        baseURL: URL,
        token: String,
        sessionConfiguration: URLSessionConfiguration?
    ) throws {
        guard Self.isAllowedEndpoint(baseURL), !token.isEmpty else {
            throw LocalAPIClientError.invalidEndpoint
        }
        self.baseURL = baseURL
        self.token = token
        self.session = URLSession(
            configuration: sessionConfiguration ?? .ephemeral,
            delegate: LocalOnlyURLSessionDelegate(),
            delegateQueue: nil
        )
    }

    func makeHealthRequest() throws -> URLRequest {
        guard let url = URL(string: "/health", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    public func health() async throws -> Bool {
        let (data, response) = try await session.data(for: makeHealthRequest())
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(HealthResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.status == "ok"
    }

    public func transcribeVoice(pcm16LE: Data) async throws -> String {
        guard !pcm16LE.isEmpty, pcm16LE.count <= 960_000, pcm16LE.count.isMultiple(of: 2) else {
            throw LocalAPIClientError.invalidResponse
        }
        guard let url = URL(string: "/voice/transcribe", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = pcm16LE

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(VoiceTranscriptionResponse.self, from: data),
              !value.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.text
    }

    public func listMemories() async throws -> [LocalMemoryItem] {
        guard let url = URL(string: "/memories", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let list = try? JSONDecoder().decode(LocalMemoryList.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return list.memories
    }

    public func listSkills() async throws -> [LocalSkillItem] {
        guard let url = URL(string: "/skills", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let list = try? JSONDecoder().decode(LocalSkillList.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return list.skills
    }

    public func memoryVersions(id: String) async throws -> [LocalMemoryVersion] {
        guard let memoryID = UUID(uuidString: id),
              let url = URL(string: "/memories/\(memoryID.uuidString.lowercased())/versions", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let list = try? JSONDecoder().decode(LocalMemoryVersionList.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return list.versions
    }

    public func memorySource(id: String) async throws -> LocalMemorySource? {
        guard let memoryID = UUID(uuidString: id),
              let url = URL(string: "/memories/\(memoryID.uuidString.lowercased())/source", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let result = try? JSONDecoder().decode(LocalMemorySourceResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return result.source
    }

    public func exportEncryptedBackup(
        destinationPath: String, password: String, replaceExisting: Bool = false
    ) async throws -> Int {
        guard destinationPath.hasPrefix("/"), destinationPath.utf8.count <= 4_096,
              let url = URL(string: "/backups/export", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(BackupExportPayload(
            destinationPath: destinationPath,
            password: password,
            replaceExisting: replaceExisting
        ))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 201 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let result = try? JSONDecoder().decode(BackupExportResponse.self, from: data), result.created else {
            throw LocalAPIClientError.invalidResponse
        }
        return result.bytesWritten
    }

    public func restoreEncryptedBackup(sourcePath: String, password: String) async throws -> String {
        guard sourcePath.hasPrefix("/"), sourcePath.utf8.count <= 4_096,
              let url = URL(string: "/backups/restore", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(BackupRestorePayload(sourcePath: sourcePath, password: password))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let result = try? JSONDecoder().decode(BackupRestoreResponse.self, from: data), result.restored else {
            throw LocalAPIClientError.invalidResponse
        }
        return result.prebackupPath
    }

    public func createConfirmedMemory(
        subject: String, content: String, category: String, sourceMessageID: String? = nil
    ) async throws -> LocalMemoryItem {
        guard let url = URL(string: "/memories", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ConfirmedMemoryPayload(
            subject: subject, content: content, category: category, confirmed: true,
            sourceMessageID: sourceMessageID
        ))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 201 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let memory = try? JSONDecoder().decode(LocalMemoryItem.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return memory
    }

    public func updateConfirmedMemory(
        id: String, subject: String, content: String, category: String
    ) async throws -> LocalMemoryItem {
        guard let memoryID = UUID(uuidString: id),
              let url = URL(string: "/memories/\(memoryID.uuidString.lowercased())", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ConfirmedMemoryPayload(
            subject: subject, content: content, category: category, confirmed: true
        ))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let memory = try? JSONDecoder().decode(LocalMemoryItem.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return memory
    }

    public func deleteMemory(id: String) async throws {
        guard let memoryID = UUID(uuidString: id),
              let url = URL(string: "/memories/\(memoryID.uuidString.lowercased())", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
    }

    public func listTasks(includeCompleted: Bool = true) async throws -> [LocalTaskItem] {
        var components = URLComponents(
            url: URL(string: "/tasks", relativeTo: baseURL)!.absoluteURL,
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [URLQueryItem(name: "include_completed", value: String(includeCompleted))]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let list = try? JSONDecoder().decode(LocalTaskList.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return list.tasks
    }

    public func createTask(
        title: String, description: String = "", priority: Int = 0, scheduleAt: String? = nil
    ) async throws -> LocalTaskItem {
        guard let url = URL(string: "/tasks", relativeTo: baseURL)?.absoluteURL else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(TaskCreatePayload(
            title: title,
            description: description,
            priority: priority,
            scheduleAt: scheduleAt,
            idempotencyKey: UUID().uuidString.lowercased()
        ))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 201 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let task = try? JSONDecoder().decode(LocalTaskItem.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return task
    }

    public func deleteTask(id: String) async throws {
        guard let taskID = UUID(uuidString: id),
              let url = URL(string: "/tasks/\(taskID.uuidString.lowercased())", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
    }

    public func transitionTask(id: String, status: String) async throws -> LocalTaskItem {
        guard let taskID = UUID(uuidString: id),
              let url = URL(string: "/tasks/\(taskID.uuidString.lowercased())/status", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(TaskTransitionPayload(status: status))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let task = try? JSONDecoder().decode(LocalTaskItem.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return task
    }

    public func conversations() async throws -> [LocalConversationItem] {
        guard let url = URL(string: "/conversations", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let list = try? JSONDecoder().decode(LocalConversationList.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return list.conversations
    }

    public func createConversation(title: String = "新对话") async throws -> LocalConversationItem {
        guard let url = URL(string: "/conversations", relativeTo: baseURL)?.absoluteURL else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ConversationCreatePayload(title: title))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 201 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let item = try? JSONDecoder().decode(LocalConversationItem.self, from: data) else { throw LocalAPIClientError.invalidResponse }
        return item
    }

    public func renameConversation(id: String, title: String) async throws -> LocalConversationItem {
        guard let conversationID = UUID(uuidString: id),
              let url = URL(string: "/conversations/\(conversationID.uuidString.lowercased())", relativeTo: baseURL)?.absoluteURL
        else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ConversationRenamePayload(title: title))
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw LocalAPIClientError.invalidResponse }
        guard httpResponse.statusCode == 200 else { throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode) }
        guard let item = try? JSONDecoder().decode(LocalConversationItem.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return item
    }

    public func chatHistory(
        conversationID: String? = nil, beforeMessageID: String? = nil, limit: Int = 100
    ) async throws -> LocalChatHistory {
        guard (1...200).contains(limit) else { throw LocalAPIClientError.invalidEndpoint }
        var components = URLComponents(
            url: URL(string: "/chat/history", relativeTo: baseURL)!.absoluteURL,
            resolvingAgainstBaseURL: false
        )!
        var queryItems = [URLQueryItem(name: "limit", value: String(limit))]
        if let conversationID {
            queryItems.append(URLQueryItem(name: "conversation_id", value: conversationID))
        }
        if let beforeMessageID {
            guard UUID(uuidString: beforeMessageID) != nil else { throw LocalAPIClientError.invalidEndpoint }
            queryItems.append(URLQueryItem(name: "before_message_id", value: beforeMessageID))
        }
        components.queryItems = queryItems
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let history = try? JSONDecoder().decode(LocalChatHistory.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return history
    }

    public func deleteChatHistory(conversationID: String) async throws {
        guard let identifier = UUID(uuidString: conversationID) else {
            throw LocalAPIClientError.invalidEndpoint
        }
        var components = URLComponents(
            url: URL(string: "/chat/history", relativeTo: baseURL)!.absoluteURL,
            resolvingAgainstBaseURL: false
        )!
        components.queryItems = [URLQueryItem(name: "conversation_id", value: identifier.uuidString.lowercased())]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
    }

    public func chatRunStatus(runID: String) async throws -> LocalChatRunStatus {
        guard let identifier = UUID(uuidString: runID),
              let url = URL(
                string: "/chat/runs/\(identifier.uuidString.lowercased())",
                relativeTo: baseURL
              )?.absoluteURL
        else {
            throw LocalAPIClientError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(ChatRunStatusResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return value.status
    }

    public func recentUsage(limit: Int = 50) async throws -> LocalUsageSnapshot {
        guard (1...100).contains(limit),
              let endpoint = URL(string: "/usage", relativeTo: baseURL),
              var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: true)
        else { throw LocalAPIClientError.invalidEndpoint }
        components.queryItems = [URLQueryItem(name: "limit", value: String(limit))]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let value = try? JSONDecoder().decode(UsageResponse.self, from: data) else {
            throw LocalAPIClientError.invalidResponse
        }
        return LocalUsageSnapshot(records: value.records, budget: value.budget)
    }

    public func importSelectedText(data: Data, fileName: String) async throws -> LocalImportedTextFile {
        let suffix = URL(fileURLWithPath: fileName).pathExtension.lowercased()
        guard !data.isEmpty, data.count <= 10 * 1024 * 1024,
              !fileName.contains("/"), !fileName.contains("\\"),
              ["txt", "md", "markdown"].contains(suffix),
              let endpoint = URL(string: "/imports/text", relativeTo: baseURL),
              var components = URLComponents(url: endpoint, resolvingAgainstBaseURL: true)
        else {
            throw LocalAPIClientError.invalidResponse
        }
        components.queryItems = [URLQueryItem(name: "filename", value: fileName)]
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = data
        let (responseData, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 201 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
        guard let imported = try? JSONDecoder().decode(LocalImportedTextFile.self, from: responseData) else {
            throw LocalAPIClientError.invalidResponse
        }
        return imported
    }

    public func removeImportedText(importID: String) async throws {
        guard let identifier = UUID(uuidString: importID),
              let url = URL(
                string: "/imports/\(identifier.uuidString.lowercased())",
                relativeTo: baseURL
              )?.absoluteURL
        else {
            throw LocalAPIClientError.invalidResponse
        }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LocalAPIClientError.invalidResponse
        }
        guard httpResponse.statusCode == 200 else {
            throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
        }
    }

    public func openVoiceStream() throws -> LocalVoiceStream {
        guard let httpURL = URL(string: "/voice/stream", relativeTo: baseURL)?.absoluteURL,
              var components = URLComponents(url: httpURL, resolvingAgainstBaseURL: false)
        else { throw LocalAPIClientError.invalidEndpoint }
        components.scheme = httpURL.scheme == "https" ? "wss" : "ws"
        guard let url = components.url else { throw LocalAPIClientError.invalidEndpoint }
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let task = session.webSocketTask(with: request)
        task.resume()
        return LocalVoiceStream(task: task)
    }

    public func streamChat(
        messages: [LocalChatMessage],
        provider: String = "ollama",
        model: String = "qwen3.5:0.8b",
        confirmedForThisRequest: Bool = false,
        importedDocumentIDs: [String] = [],
        conversationID: String? = nil,
        assistantKey: String = "main_assistant",
        skillKeys: [String] = [],
        collaboratorKeys: [String] = []
    ) -> AsyncThrowingStream<LocalChatStreamItem, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    guard let url = URL(string: "/chat/stream", relativeTo: baseURL)?.absoluteURL else {
                        throw LocalAPIClientError.invalidEndpoint
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.httpBody = try JSONEncoder().encode(ChatRequest(
                        messages: messages,
                        provider: provider,
                        model: model,
                        confirmedForThisRequest: confirmedForThisRequest,
                        importIDs: importedDocumentIDs,
                        conversationID: conversationID,
                        assistantKey: assistantKey,
                        skillKeys: skillKeys,
                        collaboratorKeys: collaboratorKeys
                    ))
                    let (bytes, response) = try await session.bytes(for: request)
                    guard let httpResponse = response as? HTTPURLResponse else {
                        throw LocalAPIClientError.invalidResponse
                    }
                    guard httpResponse.statusCode == 200 else {
                        throw LocalAPIClientError.requestFailed(statusCode: httpResponse.statusCode)
                    }
                    if let runID = httpResponse.value(forHTTPHeaderField: "X-PAC-Run-ID"),
                       let identifier = UUID(uuidString: runID) {
                        continuation.yield(.runID(identifier.uuidString.lowercased()))
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let event = try JSONDecoder().decode(
                            ChatStreamEvent.self,
                            from: Data(line.dropFirst(6).utf8)
                        )
                        if let eventRunID = event.runID,
                           let identifier = UUID(uuidString: eventRunID) {
                            continuation.yield(.runID(identifier.uuidString.lowercased()))
                        }
                        if let delta = event.delta { continuation.yield(.delta(delta)) }
                        if let message = event.error { throw LocalAPIStreamError(message: message) }
                        if event.done == true { break }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func isAllowedEndpoint(_ url: URL) -> Bool {
        let portAllowed = url.port.map { (1...65535).contains($0) } ?? true
        guard url.scheme == "http",
              let host = url.host?.lowercased(),
              host == "127.0.0.1" || host == "::1",
              url.user == nil,
              url.password == nil,
              url.query == nil,
              url.fragment == nil,
              url.path.isEmpty || url.path == "/",
              portAllowed
        else {
            return false
        }
        return true
    }
}

private struct ChatRequest: Encodable {
    let messages: [LocalChatMessage]
    let provider: String
    let model: String
    let confirmedForThisRequest: Bool
    let importIDs: [String]
    let conversationID: String?
    let assistantKey: String
    let skillKeys: [String]
    let collaboratorKeys: [String]

    enum CodingKeys: String, CodingKey {
        case messages
        case provider
        case model
        case confirmedForThisRequest = "confirmed_for_this_request"
        case importIDs = "import_ids"
        case conversationID = "conversation_id"
        case assistantKey = "assistant_key"
        case skillKeys = "skill_keys"
        case collaboratorKeys = "collaborator_keys"
    }
}

private struct ChatStreamEvent: Decodable {
    let delta: String?
    let done: Bool?
    let error: String?
    let runID: String?

    enum CodingKeys: String, CodingKey {
        case delta
        case done
        case error
        case runID = "run_id"
    }
}

private struct ChatRunStatusResponse: Decodable {
    let status: LocalChatRunStatus
}

private struct UsageResponse: Decodable {
    let records: [LocalUsageRecord]
    let budget: LocalMonthlyCloudBudget?
}

public struct LocalAPIStreamError: Error, LocalizedError {
    public let message: String
    public var errorDescription: String? { message }
}

private struct HealthResponse: Decodable {
    let status: String
}

private struct VoiceTranscriptionResponse: Decodable {
    let text: String
}

private final class LocalOnlyURLSessionDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

private struct TaskCreatePayload: Encodable {
    let title: String
    let description: String
    let priority: Int
    let scheduleAt: String?
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case title, description, priority
        case scheduleAt = "schedule_at"
        case idempotencyKey = "idempotency_key"
    }
}

private struct TaskTransitionPayload: Encodable {
    let status: String
}

private struct ConfirmedMemoryPayload: Encodable {
    let subject: String
    let content: String
    let category: String
    let confirmed: Bool
    var sourceMessageID: String? = nil

    enum CodingKeys: String, CodingKey {
        case subject, content, category, confirmed
        case sourceMessageID = "source_message_id"
    }
}

private struct ConversationCreatePayload: Encodable {
    let title: String
}

private struct ConversationRenamePayload: Encodable {
    let title: String
}
