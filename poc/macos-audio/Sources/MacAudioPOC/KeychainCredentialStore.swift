import Foundation
import Security

public enum KeychainCredentialError: Error, Equatable, LocalizedError {
    case emptyIdentity
    case emptySecret
    case keychain(operation: String, status: OSStatus)

    public var errorDescription: String? {
        switch self {
        case .emptyIdentity: "密钥账户信息无效。"
        case .emptySecret: "API Key 不能为空。"
        case .keychain(let operation, let status): "Keychain 操作失败（\(operation), \(status)）。"
        }
    }
}

/// Stores credentials in this Mac's Keychain without exposing a plaintext read API.
public final class KeychainCredentialStore {
    private let service: String

    public init(service: String) {
        self.service = service
    }

    public func save(_ secret: String, account: String) throws {
        try validate(account: account)
        guard !secret.isEmpty else { throw KeychainCredentialError.emptySecret }
        let key = baseQuery(account: account)
        let attributes = [kSecValueData as String: Data(secret.utf8)] as CFDictionary

        let updateStatus = SecItemUpdate(key as CFDictionary, attributes)
        if updateStatus == errSecSuccess { return }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainCredentialError.keychain(
                operation: "update", status: updateStatus
            )
        }

        var insert = key
        insert[kSecValueData as String] = Data(secret.utf8)
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let addStatus = SecItemAdd(insert as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainCredentialError.keychain(operation: "save", status: addStatus)
        }
    }

    public func delete(account: String) throws {
        try validate(account: account)
        let status = SecItemDelete(baseQuery(account: account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainCredentialError.keychain(operation: "delete", status: status)
        }
    }

    public func contains(account: String) throws -> Bool {
        try validate(account: account)
        var query = baseQuery(account: account)
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        query[kSecReturnAttributes as String] = false
        query[kSecReturnData as String] = false

        let status = SecItemCopyMatching(query as CFDictionary, nil)
        if status == errSecSuccess { return true }
        if status == errSecItemNotFound { return false }
        throw KeychainCredentialError.keychain(operation: "status", status: status)
    }

    private func validate(account: String) throws {
        guard !service.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !account.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw KeychainCredentialError.emptyIdentity
        }
    }

    private func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
