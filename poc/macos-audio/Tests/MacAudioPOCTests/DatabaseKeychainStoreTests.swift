import Foundation
import Security
import Testing
import UserNotifications
@testable import MacAudioPOC

private final class FakeDatabaseKeychainAccess: DatabaseKeychainAccessing {
    var copyResults: [(OSStatus, Data?)]
    var addStatuses: [OSStatus]
    var randomStatus: OSStatus = errSecSuccess
    var randomKey = Data(repeating: 0xA5, count: DatabaseKeychainStore.keyLength)
    private(set) var copyQueries: [[String: Any]] = []
    private(set) var addAttributes: [[String: Any]] = []
    private(set) var randomByteCounts: [Int] = []

    init(
        copyResults: [(OSStatus, Data?)] = [],
        addStatuses: [OSStatus] = []
    ) {
        self.copyResults = copyResults
        self.addStatuses = addStatuses
    }

    func copyMatching(query: [String: Any]) -> (OSStatus, Data?) {
        copyQueries.append(query)
        guard !copyResults.isEmpty else { return (errSecItemNotFound, nil) }
        return copyResults.removeFirst()
    }

    func add(attributes: [String: Any]) -> OSStatus {
        addAttributes.append(attributes)
        guard !addStatuses.isEmpty else { return errSecSuccess }
        return addStatuses.removeFirst()
    }

    func randomBytes(count: Int) -> (OSStatus, Data) {
        randomByteCounts.append(count)
        return (randomStatus, randomKey)
    }
}

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

@Test func databaseKeychainStoreReturnsAnExistingValidKeyWithoutMutation() throws {
    let key = Data(repeating: 0x37, count: DatabaseKeychainStore.keyLength)
    let access = FakeDatabaseKeychainAccess(copyResults: [(errSecSuccess, key)])
    let store = DatabaseKeychainStore(service: "test.service", account: "test.account", keychain: access)

    #expect(try store.loadOrCreateKey() == key)
    #expect(access.copyQueries.count == 1)
    #expect(access.addAttributes.isEmpty)
    #expect(access.randomByteCounts.isEmpty)
}

@Test func databaseKeychainStoreCreatesADeviceOnlyKeyWhenMissing() throws {
    let access = FakeDatabaseKeychainAccess(
        copyResults: [(errSecItemNotFound, nil)],
        addStatuses: [errSecSuccess]
    )
    let store = DatabaseKeychainStore(service: "test.service", account: "test.account", keychain: access)

    #expect(try store.loadOrCreateKey() == access.randomKey)
    #expect(access.randomByteCounts == [DatabaseKeychainStore.keyLength])
    #expect(access.addAttributes.count == 1)
    #expect(access.addAttributes[0][kSecValueData as String] as? Data == access.randomKey)
    #expect(
        (access.addAttributes[0][kSecAttrAccessible as String] as? String)
            == (kSecAttrAccessibleWhenUnlockedThisDeviceOnly as String)
    )
}

@Test func databaseKeychainStoreReadsTheWinningKeyAfterDuplicateCreateRace() throws {
    let installedKey = Data(repeating: 0x61, count: DatabaseKeychainStore.keyLength)
    let access = FakeDatabaseKeychainAccess(
        copyResults: [(errSecItemNotFound, nil), (errSecSuccess, installedKey)],
        addStatuses: [errSecDuplicateItem]
    )
    let store = DatabaseKeychainStore(service: "test.service", account: "test.account", keychain: access)

    #expect(try store.loadOrCreateKey() == installedKey)
    #expect(access.copyQueries.count == 2)
    #expect(access.addAttributes.count == 1)
    #expect(access.randomByteCounts == [DatabaseKeychainStore.keyLength])
}

@Test func databaseKeychainStoreFailsClosedForMalformedOrUnreadableExistingKey() {
    let malformed = FakeDatabaseKeychainAccess(copyResults: [(errSecSuccess, Data([0x01]))])
    let malformedStore = DatabaseKeychainStore(
        service: "test.service", account: "test.account", keychain: malformed
    )
    #expect(throws: DatabaseKeychainError.invalidStoredKey) {
        try malformedStore.loadOrCreateKey()
    }
    #expect(malformed.addAttributes.isEmpty)
    #expect(malformed.randomByteCounts.isEmpty)

    let unreadable = FakeDatabaseKeychainAccess(copyResults: [(-50, nil)])
    let unreadableStore = DatabaseKeychainStore(
        service: "test.service", account: "test.account", keychain: unreadable
    )
    #expect(throws: DatabaseKeychainError.keychain(operation: "read", status: -50)) {
        try unreadableStore.loadOrCreateKey()
    }
    #expect(unreadable.addAttributes.isEmpty)
    #expect(unreadable.randomByteCounts.isEmpty)
}

@Test func databaseKeychainStoreFailsClosedWhenSecureRandomOrKeychainWriteFails() {
    let randomFailure = FakeDatabaseKeychainAccess(copyResults: [(errSecItemNotFound, nil)])
    randomFailure.randomStatus = -1
    let randomFailureStore = DatabaseKeychainStore(
        service: "test.service", account: "test.account", keychain: randomFailure
    )
    #expect(throws: DatabaseKeychainError.randomGenerationFailed(-1)) {
        try randomFailureStore.loadOrCreateKey()
    }
    #expect(randomFailure.addAttributes.isEmpty)

    let writeFailure = FakeDatabaseKeychainAccess(
        copyResults: [(errSecItemNotFound, nil)], addStatuses: [-50]
    )
    let writeFailureStore = DatabaseKeychainStore(
        service: "test.service", account: "test.account", keychain: writeFailure
    )
    #expect(throws: DatabaseKeychainError.keychain(operation: "create", status: -50)) {
        try writeFailureStore.loadOrCreateKey()
    }
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
    var requests: [String] = []

    func requestAuthorization(options: UNAuthorizationOptions) async throws -> Bool {
        requestAuthorizationResult
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        currentAuthorizationStatus
    }

    func pendingNotificationIdentifiers() async -> [String] {
        requests
    }

    func removePendingNotificationRequests(withIdentifiers identifiers: [String]) {
        requests.removeAll { identifiers.contains($0) }
    }

    func add(identifier: String, title: String, date: Date) async throws {
        requests.removeAll { $0 == identifier }
        requests.append(identifier)
    }

    func seed(identifier: String) {
        requests.append(identifier)
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
    let afterDenial = await center.pendingNotificationIdentifiers()
    #expect(afterDenial == ["other.app.notification"])

    defaults.set(true, forKey: TaskReminderManager.preferenceKey)
    center.currentAuthorizationStatus = .denied
    center.seed(identifier: "pac.task.revoked")
    await manager.reconcile(tasks: [])

    #expect(!manager.isEnabled)
    let afterRevocation = await center.pendingNotificationIdentifiers()
    #expect(afterRevocation == ["other.app.notification"])
}

@available(macOS 14.0, *)
@MainActor
@Test func taskReminderGrantRebuildsEligibleRequestsAndPreservesOtherApps() async throws {
    let suiteName = "TaskReminderGrantTests-\(UUID().uuidString)"
    let defaults = try #require(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let center = FakeTaskReminderNotificationCenter()
    center.requestAuthorizationResult = true
    center.currentAuthorizationStatus = .authorized
    center.seed(identifier: "pac.task.stale")
    center.seed(identifier: "other.app.notification")
    let manager = TaskReminderManager(center: center, defaults: defaults)

    let granted = try await manager.requestAndEnable()
    #expect(granted)
    #expect(manager.isEnabled)

    let future = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600))
    let task = LocalTaskItem(
        id: "task-restored-after-launch",
        title: "synthetic",
        description: "",
        status: "READY",
        priority: 1,
        scheduleAt: future,
        startedAt: nil,
        completedAt: nil,
        allowedTransitions: nil
    )
    await manager.reconcile(tasks: [task])

    let rebuilt = await center.pendingNotificationIdentifiers()
    #expect(rebuilt == ["other.app.notification", "pac.task.task-restored-after-launch"])
}
