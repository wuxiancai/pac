import Testing
@testable import MacAudioPOC

@Test func modelPresetStoreTrimsAndPersistsOnlyConfigurationFields() throws {
    var store = LocalModelPresetStore()

    let saved = store.save(
        name: "  本机问答  ", sourceID: "local",
        localModel: " qwen3.5:0.8b ", providerID: "ollama"
    )
    #expect(saved)
    let data = try #require(store.serializedData())
    let restored = LocalModelPresetStore(serializedData: data)

    #expect(restored.presets.count == 1)
    #expect(restored.presets[0].name == "本机问答")
    #expect(restored.presets[0].localModel == "qwen3.5:0.8b")
    #expect(restored.presets[0].providerID == "ollama")
    #expect(!String(decoding: data, as: UTF8.self).localizedCaseInsensitiveContains("api_key"))
}

@Test func modelPresetStoreRejectsInvalidAndDuplicatePresets() {
    var store = LocalModelPresetStore()

    let blankName = store.save(name: " ", sourceID: "local", localModel: "qwen", providerID: "ollama")
    let blankModel = store.save(name: "空模型", sourceID: "local", localModel: " ", providerID: "ollama")
    let unknownSource = store.save(name: "未知来源", sourceID: "custom", localModel: "qwen", providerID: "ollama")
    let firstCloudPreset = store.save(name: "Work", sourceID: "cloud", localModel: "qwen", providerID: "deepseek")
    let duplicate = store.save(name: "work", sourceID: "cloud", localModel: "qwen", providerID: "deepseek")
    #expect(!blankName)
    #expect(!blankModel)
    #expect(!unknownSource)
    #expect(firstCloudPreset)
    #expect(!duplicate)
    #expect(store.presets.count == 1)
}

@Test func modelPresetStoreDeletesOnlyMatchingPreset() {
    var store = LocalModelPresetStore()
    let firstSaved = store.save(name: "one", sourceID: "local", localModel: "qwen", providerID: "ollama")
    let secondSaved = store.save(name: "two", sourceID: "local", localModel: "llama", providerID: "ollama")
    #expect(firstSaved)
    #expect(secondSaved)
    let removedID = store.presets[0].id

    store.delete(id: removedID)

    #expect(store.presets.map(\.name) == ["two"])
}
