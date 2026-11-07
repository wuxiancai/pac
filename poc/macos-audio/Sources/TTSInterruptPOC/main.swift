import Foundation
import MacAudioPOC

@main
@MainActor
@available(macOS 10.14, *)
struct TTSInterruptPOC {
    static func main() {
        let text = CommandLine.arguments.dropFirst().joined(separator: " ")
        let utterance = text.isEmpty
            ? "这是一段本机语音合成测试。按回车键可以立即打断当前播放，并清除待播语音。"
            : text
        let engine = AVSpeechEngine()
        let controller = SpeechPlaybackController(engine: engine)

        guard controller.speak(utterance) else {
            fputs("无法启动语音合成。\n", stderr)
            Foundation.exit(EXIT_FAILURE)
        }

        print("正在使用 macOS 本机语音播放。按回车键立即打断。")
        _ = readLine()
        let interrupted = controller.interrupt()
        print("interrupted=\(interrupted) speaking=\(engine.isSpeaking)")
    }
}
