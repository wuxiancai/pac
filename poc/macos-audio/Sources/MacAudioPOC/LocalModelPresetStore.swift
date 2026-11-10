import Foundation

public struct LocalModelPreset: Codable, Identifiable, Equatable, Sendable {
    public let id: UUID
    public let name: String
    public let sourceID: String
    public let localModel: String
    public let providerID: String

    public init(
        id: UUID = UUID(),
        name: String,
        sourceID: String,
        localModel: String,
        providerID: String
    ) {
        self.id = id
        self.name = name
        self.sourceID = sourceID
        self.localModel = localModel
        self.providerID = providerID
    }

    private enum CodingKeys: String, CodingKey {
        case id, name, sourceID, localModel, providerID
        case source, cloudProvider
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        localModel = try container.decode(String.self, forKey: .localModel)
        if let currentSource = try container.decodeIfPresent(String.self, forKey: .sourceID) {
            sourceID = currentSource
            providerID = try container.decode(String.self, forKey: .providerID)
        } else {
            let legacySource = try container.decode(String.self, forKey: .source)
            sourceID = legacySource
            let legacyProvider = try container.decode(String.self, forKey: .cloudProvider)
            providerID = legacySource == "local" ? "ollama" : legacyProvider
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(name, forKey: .name)
        try container.encode(sourceID, forKey: .sourceID)
        try container.encode(localModel, forKey: .localModel)
        try container.encode(providerID, forKey: .providerID)
    }

    fileprivate var hasSupportedConfiguration: Bool {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, name.count <= 32 else {
            return false
        }
        if sourceID == "local" { return providerID == "ollama" && !localModel.isEmpty }
        return sourceID == "cloud" && ["qwen-app", "deepseek", "openrouter"].contains(providerID)
    }
}

public struct LocalModelPresetStore: Sendable {
    public private(set) var presets: [LocalModelPreset]

    public init(serializedData: Data? = nil) {
        let decoded = serializedData.flatMap {
            try? JSONDecoder().decode([LocalModelPreset].self, from: $0)
        } ?? []
        presets = decoded.filter(\.hasSupportedConfiguration)
    }

    @discardableResult
    public mutating func save(
        name rawName: String,
        sourceID rawSourceID: String,
        localModel rawLocalModel: String,
        providerID rawProviderID: String
    ) -> Bool {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        let sourceID = rawSourceID.trimmingCharacters(in: .whitespacesAndNewlines)
        let localModel = rawLocalModel.trimmingCharacters(in: .whitespacesAndNewlines)
        let providerID = rawProviderID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, name.count <= 32,
              (sourceID == "local" && providerID == "ollama")
                  || (sourceID == "cloud" && ["qwen-app", "deepseek", "openrouter"].contains(providerID)),
              sourceID != "local" || !localModel.isEmpty,
              !presets.contains(where: {
                  $0.name.localizedCaseInsensitiveCompare(name) == .orderedSame
              })
        else { return false }

        presets.append(LocalModelPreset(
            name: name,
            sourceID: sourceID,
            localModel: localModel,
            providerID: providerID
        ))
        return true
    }

    public mutating func delete(id: UUID) {
        presets.removeAll { $0.id == id }
    }

    public func serializedData() -> Data? {
        try? JSONEncoder().encode(presets)
    }
}
