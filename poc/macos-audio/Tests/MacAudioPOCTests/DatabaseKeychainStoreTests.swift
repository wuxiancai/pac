import Foundation
import Testing
import UserNotifications
@testable import MacAudioPOC

@Test func databaseKeychainStoreUsesStableNonemptyIdentity() {
    #expect(DatabaseKeychainStore.keyLength == 32)
    #expect(!DatabaseKeychainStore.service.isEmpty)
    #expect(!DatabaseKeychainStore.account.isEmpty)
}

@Test func databaseKeychainErrorsProvideSafeActionableDescriptions() {
    #expect(
        DatabaseKeychainError.invalidIdentity.localizedDescription
            == "本机数据库密钥配置无效。"
    )
    #expect(
        DatabaseKeychainError.invalidStoredKey.localizedDescription
            == "Keychain 中的数据库密钥数据无效；未替换密钥或数据库。"
    )
    #expect(
        DatabaseKeychainError.randomGenerationFailed(-1).localizedDescription
            == "无法安全生成本机数据库密钥（OSStatus -1）。"
    )
    #expect(
        DatabaseKeychainError.keychain(operation: "read", status: -50).localizedDescription
            == "无法从本机 Keychain 读取数据库密钥（OSStatus -50）。"
    )
    #expect(
        DatabaseKeychainError.keychain(operation: "create", status: -50).localizedDescription
            == "无法从本机 Keychain 保存数据库密钥（OSStatus -50）。"
    )
}

@available(macOS 14.0, *)
@MainActor
@Test func taskReminderIdentifiersUseStableAppOwnedPrefix() {
    #expect(TaskReminderManager.identifier(for: "task-123") == "pac.task.task-123")
}

@available(macOS 14.0, *)
@MainActor
@Test func taskReminderEligibilityRequiresFutureParseableScheduleAndActiveTask() {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let future = ISO8601DateFormatter().string(from: now.addingTimeInterval(60))
    let past = ISO8601DateFormatter().string(from: now.addingTimeInterval(-60))

    func task(status: String = "OPEN", scheduleAt: String?) -> LocalTaskItem {
        LocalTaskItem(
            id: "task-123",
            title: "synthetic",
            description: "",
            status: status,
            priority: 1,
            scheduleAt: scheduleAt,
            startedAt: nil,
            completedAt: nil,
            allowedTransitions: nil
        )
    }

    #expect(TaskReminderManager.isEligible(task(scheduleAt: future), now: now))
    #expect(!TaskReminderManager.isEligible(task(scheduleAt: past), now: now))
    #expect(!TaskReminderManager.isEligible(task(scheduleAt: "invalid"), now: now))
    #expect(!TaskReminderManager.isEligible(task(scheduleAt: nil), now: now))
    #expect(!TaskReminderManager.isEligible(task(status: "COMPLETED", scheduleAt: future), now: now))
    #expect(!TaskReminderManager.isEligible(task(status: "CANCELLED", scheduleAt: future), now: now))
}

@MainActor
private final class FakeTaskReminderNotificationCenter: TaskReminderNotificationCenter {
    var requestAuthorizationResult = false
    var currentAuthorizationStatus: UNAuthorizationStatus = .notDetermined
    var requests: [UNNotificationRequest] = []

    func requestAuthorization(options: UNAuthorizationOptions) async throws -> Bool {
        requestAuthorizationResult
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        currentAuthorizationStatus
    }

    func pendingNotificationRequests() async -> [UNNotificationRequest] {
        requests
    }

    func removePendingNotificationRequests(withIdentifiers identifiers: [String]) {
        requests.removeAll { identifiers.contains($0.identifier) }
    }

    func add(_ request: UNNotificationRequest) async throws {
        requests.removeAll { $0.identifier == request.identifier }
        requests.append(request)
    }

    func seed(identifier: String) {
        requests.append(
            UNNotificationRequest(
                identifier: identifier,
                content: UNMutableNotificationContent(),
                trigger: nil
            )
        )
    }
}

@available(macOS 14.0, *)
@MainActor
@Test func taskReminderDenialAndRevocationDisableAndClearOnlyOwnedRequests() async throws {
    let suiteName = "TaskReminderTests-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let center = FakeTaskReminderNotificationCenter()
    center.seed(identifier: "pac.task.old")
    center.seed(identifier: "other.app.notification")
    let manager = TaskReminderManager(center: center, defaults: defaults)

    let granted = try await manager.requestAndEnable()
    #expect(!granted)
    #expect(!manager.isEnabled)
    let afterDenial = await center.pendingNotificationRequests().map(\.identifier)
    #expect(afterDenial == ["other.app.notification"])

    defaults.set(true, forKey: TaskReminderManager.preferenceKey)
    center.currentAuthorizationStatus = .denied
    center.seed(identifier: "pac.task.revoked")
    await manager.reconcile(tasks: [])

    #expect(!manager.isEnabled)
    let afterRevocation = await center.pendingNotificationRequests().map(\.identifier)
    #expect(afterRevocation == ["other.app.notification"])
}
