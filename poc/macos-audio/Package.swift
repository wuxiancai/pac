// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MacAudioPOC",
    products: [
        .library(name: "MacAudioPOC", targets: ["MacAudioPOC"]),
        .executable(name: "tts-interrupt-poc", targets: ["TTSInterruptPOC"]),
    ],
    targets: [
        .target(name: "MacAudioPOC"),
        .executableTarget(name: "TTSInterruptPOC", dependencies: ["MacAudioPOC"]),
        .testTarget(name: "MacAudioPOCTests", dependencies: ["MacAudioPOC"]),
    ]
)
