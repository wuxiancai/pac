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
