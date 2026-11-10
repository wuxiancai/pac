import Foundation
import UserNotifications

@MainActor
@available(macOS 14.0, *)
protocol TaskReminderNotificationCenter {
    func requestAuthorization(options: UNAuthorizationOptions) async throws -> Bool
    func authorizationStatus() async -> UNAuthorizationStatus
    func pendingNotificationIdentifiers() async -> [String]
    func removePendingNotificationRequests(withIdentifiers identifiers: [String])
    func add(identifier: String, title: String, date: Date) async throws
}

@MainActor
@available(macOS 14.0, *)
private final class SystemTaskReminderNotificationCenter: TaskReminderNotificationCenter {
    private let center: UNUserNotificationCenter

    init(center: UNUserNotificationCenter = .current()) {
        self.center = center
    }

    func requestAuthorization(options: UNAuthorizationOptions) async throws -> Bool {
        try await withCheckedThrowingContinuation { continuation in
            center.requestAuthorization(options: options) { granted, error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume(returning: granted) }
            }
        }
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await withCheckedContinuation { continuation in
            center.getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    func pendingNotificationIdentifiers() async -> [String] {
        await withCheckedContinuation { continuation in
            center.getPendingNotificationRequests { requests in
                continuation.resume(returning: requests.map(\.identifier))
            }
        }
    }

    func removePendingNotificationRequests(withIdentifiers identifiers: [String]) {
        center.removePendingNotificationRequests(withIdentifiers: identifiers)
    }

    func add(identifier: String, title: String, date: Date) async throws {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = "本机任务提醒"
        content.sound = .default
        let components = Calendar.current.dateComponents(
            [.year, .month, .day, .hour, .minute, .second], from: date
        )
        let request = UNNotificationRequest(
            identifier: identifier,
            content: content,
            trigger: UNCalendarNotificationTrigger(dateMatching: components, repeats: false)
        )
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            center.add(request) { error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume() }
            }
        }
    }
}

@available(macOS 14.0, *)
@MainActor
public final class TaskReminderManager {
    public static let shared = TaskReminderManager()
    public static let preferenceKey = "beta.tasks.notifications.enabled"

    private let center: any TaskReminderNotificationCenter
    private let defaults: UserDefaults

    public init(center: UNUserNotificationCenter = .current()) {
        self.center = SystemTaskReminderNotificationCenter(center: center)
        defaults = .standard
    }

    init(center: any TaskReminderNotificationCenter, defaults: UserDefaults) {
        self.center = center
        self.defaults = defaults
    }

    public var isEnabled: Bool {
        defaults.bool(forKey: Self.preferenceKey)
    }

    /// Called only from an explicit user action in the task reminder controls.
    public func requestAndEnable() async throws -> Bool {
        let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
        if granted {
            defaults.set(true, forKey: Self.preferenceKey)
        } else {
            await disable()
        }
        return granted
    }

    public func disable() async {
        defaults.set(false, forKey: Self.preferenceKey)
        let identifiers = await center.pendingNotificationIdentifiers().filter { $0.hasPrefix("pac.task.") }
        center.removePendingNotificationRequests(withIdentifiers: identifiers)
    }

    public func reconcile(tasks: [LocalTaskItem]) async {
        guard isEnabled else { return }
        let authorization = await center.authorizationStatus()
        guard authorization == .authorized || authorization == .provisional else {
            await disable()
            return
        }
        let now = Date()
        let eligible = tasks.filter { Self.isEligible($0, now: now) }
        let keep = Set(eligible.map { Self.identifier(for: $0.id) })
        let pending = await center.pendingNotificationIdentifiers()
        let stale = pending.filter {
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

        let authorization = await center.authorizationStatus()
        guard authorization == .authorized || authorization == .provisional else {
            await disable()
            return
        }
        try? await center.add(identifier: Self.identifier(for: task.id), title: task.title, date: date)
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
