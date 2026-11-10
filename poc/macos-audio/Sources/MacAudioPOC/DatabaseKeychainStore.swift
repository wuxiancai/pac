import Foundation
import Security

public enum DatabaseKeychainError: Error, Equatable {
    case invalidIdentity
    case invalidStoredKey
    case randomGenerationFailed(OSStatus)
    case keychain(operation: String, status: OSStatus)
}

extension DatabaseKeychainError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case .invalidIdentity:
            return "本机数据库密钥配置无效。"
        case .invalidStoredKey:
            return "Keychain 中的数据库密钥数据无效；未替换密钥或数据库。"
        case .randomGenerationFailed(let status):
            return "无法安全生成本机数据库密钥（OSStatus \(status)）。"
        case .keychain(let operation, let status):
            let action = switch operation {
            case "read": "读取"
            case "create": "保存"
            default: "访问"
            }
            return "无法从本机 Keychain \(action)数据库密钥（OSStatus \(status)）。"
        }
    }
}

/// Keeps the installation's SQLCipher key in the unlocked user's Keychain.
/// The item is device-only and never requires per-launch user presence.
public final class DatabaseKeychainStore {
    public static let keyLength = 32
    public static let service = "com.personal-ai-assistant.beta.database"
    public static let account = "sqlcipher-key-v1"

    private let serviceName: String
    private let accountName: String

    public init(
        service: String = DatabaseKeychainStore.service,
        account: String = DatabaseKeychainStore.account
    ) {
        self.serviceName = service
        self.accountName = account
    }

    public func loadOrCreateKey() throws -> Data {
        try validateIdentity()
        let query = baseQuery()
        var result: CFTypeRef?
        let readStatus = SecItemCopyMatching(
            query.merging([
                kSecReturnData as String: true,
                kSecMatchLimit as String: kSecMatchLimitOne,
            ]) { _, new in new } as CFDictionary,
            &result
        )
        if readStatus == errSecSuccess {
            guard let key = result as? Data, key.count == Self.keyLength else {
                throw DatabaseKeychainError.invalidStoredKey
            }
            return key
        }
        guard readStatus == errSecItemNotFound else {
            throw DatabaseKeychainError.keychain(operation: "read", status: readStatus)
        }

        var bytes = [UInt8](repeating: 0, count: Self.keyLength)
        let randomStatus = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        guard randomStatus == errSecSuccess else {
            throw DatabaseKeychainError.randomGenerationFailed(randomStatus)
        }
        let key = Data(bytes)
        var insert = baseQuery()
        insert[kSecValueData as String] = key
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let addStatus = SecItemAdd(insert as CFDictionary, nil)
        if addStatus == errSecSuccess { return key }
        // Another app start may win the create race. Read the installed key;
        // never replace a key that may already protect an existing database.
        if addStatus == errSecDuplicateItem {
            return try loadExistingKey()
        }
        throw DatabaseKeychainError.keychain(operation: "create", status: addStatus)
    }

    private func loadExistingKey() throws -> Data {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else {
            throw DatabaseKeychainError.keychain(operation: "read", status: status)
        }
        guard let key = result as? Data, key.count == Self.keyLength else {
            throw DatabaseKeychainError.invalidStoredKey
        }
        return key
    }

    private func validateIdentity() throws {
        guard !serviceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !accountName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw DatabaseKeychainError.invalidIdentity
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: serviceName,
            kSecAttrAccount as String: accountName,
        ]
    }
}
