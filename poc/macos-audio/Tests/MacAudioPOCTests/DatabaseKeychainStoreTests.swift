import Foundation
import Testing
@testable import MacAudioPOC

@Test func databaseKeychainStoreUsesStableNonemptyIdentity() {
    #expect(DatabaseKeychainStore.keyLength == 32)
    #expect(!DatabaseKeychainStore.service.isEmpty)
    #expect(!DatabaseKeychainStore.account.isEmpty)
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
