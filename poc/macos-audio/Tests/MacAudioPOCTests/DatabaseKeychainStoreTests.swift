import Testing
@testable import MacAudioPOC

@Test func databaseKeychainStoreUsesStableNonemptyIdentity() {
    #expect(DatabaseKeychainStore.keyLength == 32)
    #expect(!DatabaseKeychainStore.service.isEmpty)
    #expect(!DatabaseKeychainStore.account.isEmpty)
}
