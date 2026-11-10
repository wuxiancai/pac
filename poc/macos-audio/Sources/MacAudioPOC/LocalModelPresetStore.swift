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
}

public struct LocalModelPresetStore: Sendable {
    public private(set) var presets: [LocalModelPreset]

    public init(serializedData: Data? = nil) {
        presets = serializedData.flatMap {
            try? JSONDecoder().decode([LocalModelPreset].self, from: $0)
        } ?? []
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
              sourceID == "local" || sourceID == "cloud",
              sourceID != "local" || !localModel.isEmpty,
              sourceID != "cloud" || !providerID.isEmpty,
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
