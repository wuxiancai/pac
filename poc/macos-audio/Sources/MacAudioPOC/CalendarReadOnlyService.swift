import EventKit
import Foundation
import Observation

public enum CalendarAccessState: Sendable, Equatable {
    case notDetermined
    case fullAccess
    case writeOnly
    case denied
    case restricted
}

public struct LocalCalendarEvent: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let calendarTitle: String
    public let startDate: Date
    public let endDate: Date
    public let isAllDay: Bool
}

@MainActor
public protocol CalendarEventReading: AnyObject {
    var authorization: CalendarAccessState { get }
    func requestFullAccess() async throws -> Bool
    func events(from start: Date, to end: Date) -> [LocalCalendarEvent]
}

@MainActor
@available(macOS 14.0, *)
private final class EventKitCalendarReader: CalendarEventReading {
    private let eventStore = EKEventStore()

    var authorization: CalendarAccessState {
        switch EKEventStore.authorizationStatus(for: .event) {
        case .fullAccess: .fullAccess
        case .writeOnly: .writeOnly
        case .denied: .denied
        case .restricted: .restricted
        case .notDetermined: .notDetermined
        @unknown default: .restricted
        }
    }

    func requestFullAccess() async throws -> Bool {
        try await eventStore.requestFullAccessToEvents()
    }

    func events(from start: Date, to end: Date) -> [LocalCalendarEvent] {
        let predicate = eventStore.predicateForEvents(
            withStart: start,
            end: end,
            calendars: nil
        )
        return eventStore.events(matching: predicate).map { event in
            LocalCalendarEvent(
                id: event.eventIdentifier ?? UUID().uuidString,
                title: event.title ?? "（无标题）",
                calendarTitle: event.calendar.title,
                startDate: event.startDate,
                endDate: event.endDate,
                isAllDay: event.isAllDay
            )
        }
    }
}

@MainActor
@Observable
@available(macOS 14.0, *)
public final class CalendarReadOnlyService {
    private let reader: any CalendarEventReading
    public private(set) var events: [LocalCalendarEvent] = []
    public private(set) var status = "点击后读取未来 30 天的本机日历。"
    public private(set) var isLoading = false

    public init() {
        reader = EventKitCalendarReader()
    }

    init(reader: any CalendarEventReading) {
        self.reader = reader
    }

    public func loadUpcomingEvents(now: Date = Date()) async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            switch reader.authorization {
            case .fullAccess:
                break
            case .notDetermined:
                guard try await reader.requestFullAccess() else {
                    events = []
                    status = "尚未获得日历访问授权。"
                    return
                }
            case .writeOnly, .denied, .restricted:
                events = []
                status = "没有读取权限；可在 macOS 系统设置的隐私与安全性中修改。"
                return
            }
            let end = Calendar.current.date(byAdding: .day, value: 30, to: now) ?? now
            events = reader.events(from: now, to: end).sorted { $0.startDate < $1.startDate }
            status = events.isEmpty ? "未来 30 天没有日历事件。" : "未来 30 天 · \(events.count) 项 · 只读"
        } catch {
            events = []
            status = "无法读取本机日历。"
        }
    }
}

public struct LocalCalendarReminder: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let listTitle: String
    public let dueDate: Date?
    public let isCompleted: Bool
}

@MainActor
public protocol CalendarReminderReading: AnyObject {
    var authorization: CalendarAccessState { get }
    func requestFullAccess() async throws -> Bool
    func incompleteReminders(dueBy end: Date) async throws -> [LocalCalendarReminder]
}

@MainActor
@available(macOS 14.0, *)
private final class EventKitCalendarReminderReader: CalendarReminderReading {
    private let eventStore = EKEventStore()

    var authorization: CalendarAccessState {
        switch EKEventStore.authorizationStatus(for: .reminder) {
        case .fullAccess: .fullAccess
        case .writeOnly: .writeOnly
        case .denied: .denied
        case .restricted: .restricted
        case .notDetermined: .notDetermined
        @unknown default: .restricted
        }
    }

    func requestFullAccess() async throws -> Bool {
        try await eventStore.requestFullAccessToReminders()
    }

    func incompleteReminders(dueBy end: Date) async throws -> [LocalCalendarReminder] {
        let predicate = eventStore.predicateForIncompleteReminders(
            withDueDateStarting: nil,
            ending: end,
            calendars: nil
        )
        let fetched = await withCheckedContinuation { (continuation: CheckedContinuation<[LocalCalendarReminder], Never>) in
            eventStore.fetchReminders(matching: predicate) { reminders in
                let values = (reminders ?? []).map { reminder in
                    LocalCalendarReminder(
                        id: reminder.calendarItemIdentifier,
                        title: reminder.title ?? "（无标题）",
                        listTitle: reminder.calendar.title,
                        dueDate: reminder.dueDateComponents.flatMap {
                            Calendar.current.date(from: $0)
                        },
                        isCompleted: reminder.isCompleted
                    )
                }
                continuation.resume(returning: values)
            }
        }
        return fetched
    }
}

@MainActor
@Observable
@available(macOS 14.0, *)
public final class CalendarRemindersReadOnlyService {
    private let reader: any CalendarReminderReading
    public private(set) var reminders: [LocalCalendarReminder] = []
    public private(set) var status = "点击后读取到期日为未来 30 天内的未完成提醒事项。"
    public private(set) var isLoading = false

    public init() {
        reader = EventKitCalendarReminderReader()
    }

    init(reader: any CalendarReminderReading) {
        self.reader = reader
    }

    public func loadUpcomingReminders(now: Date = Date()) async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            switch reader.authorization {
            case .fullAccess:
                break
            case .notDetermined:
                guard try await reader.requestFullAccess() else {
                    reminders = []
                    status = "尚未获得提醒事项访问授权。"
                    return
                }
            case .writeOnly, .denied, .restricted:
                reminders = []
                status = "没有读取权限；可在 macOS 系统设置的隐私与安全性中修改。"
                return
            }
            let end = Calendar.current.date(byAdding: .day, value: 30, to: now) ?? now
            reminders = try await reader.incompleteReminders(dueBy: end).sorted {
                switch ($0.dueDate, $1.dueDate) {
                case let (left?, right?): left < right
                case (_?, nil): true
                case (nil, _?): false
                case (nil, nil): $0.title.localizedStandardCompare($1.title) == .orderedAscending
                }
            }
            status = reminders.isEmpty
                ? "未来 30 天没有未完成提醒事项。"
                : "未完成提醒事项 · \(reminders.count) 项 · 只读"
        } catch {
            reminders = []
            status = "无法读取本机提醒事项。"
        }
    }
}
