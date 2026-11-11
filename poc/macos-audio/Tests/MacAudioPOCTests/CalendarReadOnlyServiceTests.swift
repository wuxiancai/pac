import Foundation
import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeCalendarEventReader: CalendarEventReading {
    var authorization: CalendarAccessState = .notDetermined
    var requestResult = true
    var requestCount = 0
    var requestedRange: (Date, Date)?
    var fixtures: [LocalCalendarEvent] = []

    func requestFullAccess() async throws -> Bool {
        requestCount += 1
        if requestResult { authorization = .fullAccess }
        return requestResult
    }

    func events(from start: Date, to end: Date) -> [LocalCalendarEvent] {
        requestedRange = (start, end)
        return fixtures
    }
}

@MainActor
private final class FakeCalendarReminderReader: CalendarReminderReading {
    var authorization: CalendarAccessState = .notDetermined
    var requestResult = true
    var requestCount = 0
    var requestedEndDate: Date?
    var fixtures: [LocalCalendarReminder] = []

    func requestFullAccess() async throws -> Bool {
        requestCount += 1
        if requestResult { authorization = .fullAccess }
        return requestResult
    }

    func incompleteReminders(dueBy end: Date) async throws -> [LocalCalendarReminder] {
        requestedEndDate = end
        return fixtures
    }
}

@available(macOS 14.0, *)
@Test @MainActor func calendarReaderRequestsPermissionOnlyAfterExplicitLoadAndLimitsToThirtyDays() async throws {
    let reader = FakeCalendarEventReader()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let earlier = LocalCalendarEvent(
        id: "earlier", title: "Planning", calendarTitle: "Work",
        startDate: now.addingTimeInterval(60), endDate: now.addingTimeInterval(3_660), isAllDay: false
    )
    let later = LocalCalendarEvent(
        id: "later", title: "Review", calendarTitle: "Work",
        startDate: now.addingTimeInterval(7_200), endDate: now.addingTimeInterval(10_800), isAllDay: false
    )
    reader.fixtures = [later, earlier]
    let service = CalendarReadOnlyService(reader: reader)

    #expect(reader.requestCount == 0)
    await service.loadUpcomingEvents(now: now)

    #expect(reader.requestCount == 1)
    #expect(service.events.map(\.id) == ["earlier", "later"])
    #expect(reader.requestedRange?.0 == now)
    #expect(reader.requestedRange?.1 == Calendar.current.date(byAdding: .day, value: 30, to: now))
    #expect(service.status.contains("只读"))
}

@available(macOS 14.0, *)
@Test @MainActor func calendarReaderDoesNotFetchWhenAuthorizationIsDenied() async {
    let reader = FakeCalendarEventReader()
    reader.authorization = .denied
    let service = CalendarReadOnlyService(reader: reader)

    await service.loadUpcomingEvents()

    #expect(reader.requestCount == 0)
    #expect(reader.requestedRange == nil)
    #expect(service.events.isEmpty)
}

@available(macOS 14.0, *)
@Test @MainActor func calendarReaderRequestDenialExplainsHowToEnablePermission() async {
    let reader = FakeCalendarEventReader()
    reader.requestResult = false
    let service = CalendarReadOnlyService(reader: reader)

    await service.loadUpcomingEvents()

    #expect(reader.requestCount == 1)
    #expect(reader.requestedRange == nil)
    #expect(service.events.isEmpty)
    #expect(service.status.contains("系统设置的隐私与安全性"))
}

@available(macOS 14.0, *)
@Test @MainActor func remindersReaderRequestsPermissionAfterClickAndSortsDueDates() async {
    let reader = FakeCalendarReminderReader()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let later = LocalCalendarReminder(
        id: "later", title: "Review", listTitle: "Work",
        dueDate: now.addingTimeInterval(7_200), isCompleted: false
    )
    let earlier = LocalCalendarReminder(
        id: "earlier", title: "Plan", listTitle: "Work",
        dueDate: now.addingTimeInterval(60), isCompleted: false
    )
    let undated = LocalCalendarReminder(
        id: "undated", title: "Someday", listTitle: "Personal",
        dueDate: nil, isCompleted: false
    )
    reader.fixtures = [later, undated, earlier]
    let service = CalendarRemindersReadOnlyService(reader: reader)

    #expect(reader.requestCount == 0)
    await service.loadUpcomingReminders(now: now)

    #expect(reader.requestCount == 1)
    #expect(service.reminders.map(\.id) == ["earlier", "later", "undated"])
    #expect(reader.requestedEndDate == Calendar.current.date(byAdding: .day, value: 30, to: now))
    #expect(service.status.contains("只读"))
}

@available(macOS 14.0, *)
@Test @MainActor func remindersReaderDoesNotFetchWhenAuthorizationIsDenied() async {
    let reader = FakeCalendarReminderReader()
    reader.authorization = .denied
    let service = CalendarRemindersReadOnlyService(reader: reader)

    await service.loadUpcomingReminders()

    #expect(reader.requestCount == 0)
    #expect(reader.requestedEndDate == nil)
    #expect(service.reminders.isEmpty)
}

@available(macOS 14.0, *)
@Test @MainActor func remindersReaderRequestDenialExplainsHowToEnablePermission() async {
    let reader = FakeCalendarReminderReader()
    reader.requestResult = false
    let service = CalendarRemindersReadOnlyService(reader: reader)

    await service.loadUpcomingReminders()

    #expect(reader.requestCount == 1)
    #expect(reader.requestedEndDate == nil)
    #expect(service.reminders.isEmpty)
    #expect(service.status.contains("系统设置的隐私与安全性"))
}
