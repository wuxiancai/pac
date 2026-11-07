// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MacAudioPOC",
    products: [
        .library(name: "MacAudioPOC", targets: ["MacAudioPOC"]),
        .executable(name: "tts-interrupt-poc", targets: ["TTSInterruptPOC"]),
        .executable(name: "local-api-client-poc", targets: ["LocalAPIClientPOC"]),
        .executable(name: "backend-lifecycle-poc", targets: ["BackendLifecyclePOC"]),
    ],
    targets: [
        .target(name: "MacAudioPOC"),
        .executableTarget(name: "TTSInterruptPOC", dependencies: ["MacAudioPOC"]),
        .executableTarget(name: "LocalAPIClientPOC", dependencies: ["MacAudioPOC"]),
        .executableTarget(name: "BackendLifecyclePOC", dependencies: ["MacAudioPOC"]),
        .testTarget(name: "MacAudioPOCTests", dependencies: ["MacAudioPOC"]),
    ]
)
