import Foundation
import MacAudioPOC

@main
@MainActor
@available(macOS 10.14, *)
struct TTSInterruptPOC {
    static func main() {
        var arguments = Array(CommandLine.arguments.dropFirst())
        let waitForCompletion = arguments.first == "--wait-for-completion"
        if waitForCompletion {
            arguments.removeFirst()
        }
        let text = arguments.joined(separator: " ")
        let utterance = text.isEmpty
            ? "这是一段本机语音合成测试。按回车键可以立即打断当前播放，并清除待播语音。"
            : text
        let engine = AVSpeechEngine()
        let controller = SpeechPlaybackController(engine: engine)

        guard controller.speak(utterance) == .started else {
            fputs("无法启动语音合成。\n", stderr)
            Foundation.exit(EXIT_FAILURE)
        }

        if waitForCompletion {
            guard waitUntilSpeechFinishes(engine, timeout: 45) else {
                fputs("语音播放未在 45 秒内完成。\n", stderr)
                Foundation.exit(EXIT_FAILURE)
            }
            print("playback_completed=true speaking=false")
            return
        }

        print("正在使用 macOS 本机语音播放。按回车键立即打断。")
        _ = readLine()
        let interrupted = controller.interrupt()
        print("interrupted=\(interrupted) speaking=\(engine.isSpeaking)")
    }

    private static func waitUntilSpeechFinishes(
        _ engine: AVSpeechEngine,
        timeout: TimeInterval
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        var observedSpeaking = engine.isSpeaking
        while Date() < deadline {
            if engine.isSpeaking {
                observedSpeaking = true
            } else if observedSpeaking {
                return true
            }
            RunLoop.main.run(until: Date().addingTimeInterval(0.02))
        }
        return false
    }
}
