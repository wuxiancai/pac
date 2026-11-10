import Foundation
import Testing
@testable import MacAudioPOC

@MainActor
private final class FakeCalendarEventWriter: CalendarEventWriting {
    var authorization: CalendarAccessState = .notDetermined
    var hasDefaultCalendarForNewEvents = true
    var requestResult = true
    var requestCount = 0
    var saves: [CalendarEventDraft] = []
    var shouldThrowOnSave = false

    func requestWriteOnlyAccess() async throws -> Bool {
        requestCount += 1
        if requestResult { authorization = .writeOnly }
        return requestResult
    }

    func save(_ draft: CalendarEventDraft) throws {
        if shouldThrowOnSave { throw TestWriterError.saveFailed }
        saves.append(draft)
    }
}

private enum TestWriterError: Error { case saveFailed }

@available(macOS 14.0, *)
@Test @MainActor func calendarCreationPreparationRequestsPermissionButNeverWrites() async {
    let writer = FakeCalendarEventWriter()
    let service = CalendarEventCreationService(writer: writer)

    #expect(await service.prepareForEventCreation())
    #expect(writer.requestCount == 1)
    #expect(writer.saves.isEmpty)
    #expect(service.isReadyToCreate)
}

@available(macOS 14.0, *)
@Test @MainActor func calendarCreationRequiresPreparationAndValidDraft() async throws {
    let writer = FakeCalendarEventWriter()
    writer.authorization = .writeOnly
    let service = CalendarEventCreationService(writer: writer)
    let start = Date(timeIntervalSince1970: 1_800_000_000)
    let valid = CalendarEventDraft(title: "  Planning  ", startDate: start, endDate: start.addingTimeInterval(3600))

    #expect(throws: CalendarEventCreationError.authorizationRequired) {
        try service.createApprovedEvent(valid)
    }
    #expect(await service.prepareForEventCreation())
    #expect(throws: CalendarEventCreationError.invalidTitle) {
        try service.createApprovedEvent(CalendarEventDraft(title: "  ", startDate: start, endDate: start.addingTimeInterval(60)))
    }
    #expect(writer.saves.isEmpty)

    try service.createApprovedEvent(valid)
    #expect(writer.saves.count == 1)
    #expect(writer.saves[0].title == "Planning")
}

@available(macOS 14.0, *)
@Test @MainActor func calendarCreationFailsClosedWithoutPermissionOrDefaultCalendar() async {
    let deniedWriter = FakeCalendarEventWriter()
    deniedWriter.authorization = .denied
    let deniedService = CalendarEventCreationService(writer: deniedWriter)
    #expect(!(await deniedService.prepareForEventCreation()))
    #expect(deniedWriter.requestCount == 0)
    #expect(deniedWriter.saves.isEmpty)

    let noCalendarWriter = FakeCalendarEventWriter()
    noCalendarWriter.authorization = .writeOnly
    noCalendarWriter.hasDefaultCalendarForNewEvents = false
    let noCalendarService = CalendarEventCreationService(writer: noCalendarWriter)
    #expect(!(await noCalendarService.prepareForEventCreation()))
    #expect(!noCalendarService.isReadyToCreate)
}

@available(macOS 14.0, *)
@Test @MainActor func calendarCreationPropagatesSaveFailureWithoutRetrying() async throws {
    let writer = FakeCalendarEventWriter()
    writer.authorization = .fullAccess
    writer.shouldThrowOnSave = true
    let service = CalendarEventCreationService(writer: writer)
    #expect(await service.prepareForEventCreation())
    let start = Date(timeIntervalSince1970: 1_800_000_000)

    #expect(throws: TestWriterError.saveFailed) {
        try service.createApprovedEvent(CalendarEventDraft(title: "Planning", startDate: start, endDate: start.addingTimeInterval(60)))
    }
    #expect(writer.saves.isEmpty)
}
