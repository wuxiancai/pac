import Foundation
import UserNotifications

@available(macOS 14.0, *)
@MainActor
public final class TaskReminderManager {
    public static let shared = TaskReminderManager()
    public static let preferenceKey = "beta.tasks.notifications.enabled"

    private let center: UNUserNotificationCenter

    public init(center: UNUserNotificationCenter = .current()) {
        self.center = center
    }

    public var isEnabled: Bool {
        UserDefaults.standard.bool(forKey: Self.preferenceKey)
    }

    /// Called only from an explicit user action in the task reminder controls.
    public func requestAndEnable() async throws -> Bool {
        let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
        if granted {
            UserDefaults.standard.set(true, forKey: Self.preferenceKey)
        } else {
            await disable()
        }
        return granted
    }

    public func disable() async {
        UserDefaults.standard.set(false, forKey: Self.preferenceKey)
        let requests = await center.pendingNotificationRequests()
        let identifiers = requests.map(\.identifier).filter { $0.hasPrefix("pac.task.") }
        center.removePendingNotificationRequests(withIdentifiers: identifiers)
    }

    public func reconcile(tasks: [LocalTaskItem]) async {
        guard isEnabled else { return }
        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
            await disable()
            return
        }
        let now = Date()
        let eligible = tasks.filter { Self.isEligible($0, now: now) }
        let keep = Set(eligible.map { Self.identifier(for: $0.id) })
        let pending = await center.pendingNotificationRequests()
        let stale = pending.map(\.identifier).filter {
            $0.hasPrefix("pac.task.") && !keep.contains($0)
        }
        center.removePendingNotificationRequests(withIdentifiers: stale)
        for task in eligible {
            await schedule(task: task)
        }
    }

    public func schedule(task: LocalTaskItem) async {
        guard isEnabled else { return }
        guard Self.isEligible(task, now: Date()),
              let scheduledAt = task.scheduleAt,
              let date = Self.parseDate(scheduledAt)
        else {
            remove(taskID: task.id)
            return
        }

        let settings = await center.notificationSettings()
        guard settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional else {
            await disable()
            return
        }
        let content = UNMutableNotificationContent()
        content.title = task.title
        content.body = "本机任务提醒"
        content.sound = .default
        let trigger = UNCalendarNotificationTrigger(
            dateMatching: Calendar.current.dateComponents(
                [.year, .month, .day, .hour, .minute, .second], from: date
            ),
            repeats: false
        )
        let request = UNNotificationRequest(
            identifier: Self.identifier(for: task.id), content: content, trigger: trigger
        )
        try? await center.add(request)
    }

    public func remove(taskID: String) {
        center.removePendingNotificationRequests(withIdentifiers: [Self.identifier(for: taskID)])
    }

    public static func identifier(for taskID: String) -> String {
        "pac.task.\(taskID)"
    }

    static func isEligible(_ task: LocalTaskItem, now: Date) -> Bool {
        guard !["COMPLETED", "CANCELLED"].contains(task.status),
              let scheduledAt = task.scheduleAt,
              let date = parseDate(scheduledAt)
        else { return false }
        return date > now
    }

    private static func parseDate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let standard = ISO8601DateFormatter()
        standard.formatOptions = [.withInternetDateTime]
        return standard.date(from: value)
    }
}
