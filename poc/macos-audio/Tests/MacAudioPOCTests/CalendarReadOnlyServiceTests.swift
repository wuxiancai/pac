import Foundation
import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeCalendarEventReader: CalendarEventReading {
    var authorization: CalendarAccessState = .notDetermined
    var requestCount = 0
    var requestedRange: (Date, Date)?
    var fixtures: [LocalCalendarEvent] = []

    func requestFullAccess() async throws -> Bool {
        requestCount += 1
        authorization = .fullAccess
        return true
    }

    func events(from start: Date, to end: Date) -> [LocalCalendarEvent] {
        requestedRange = (start, end)
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
