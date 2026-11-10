import EventKit
import Foundation
import Observation

public struct CalendarEventDraft: Equatable, Sendable {
    public let title: String
    public let startDate: Date
    public let endDate: Date
    public let location: String?
    public let notes: String?

    public init(title: String, startDate: Date, endDate: Date, location: String? = nil, notes: String? = nil) {
        self.title = title
        self.startDate = startDate
        self.endDate = endDate
        self.location = location
        self.notes = notes
    }
}

public enum CalendarEventCreationError: Error, Equatable {
    case invalidTitle
    case invalidDateRange
    case fieldTooLong
    case authorizationRequired
    case defaultCalendarUnavailable
    case eventAlreadyCreated
}

@MainActor
public protocol CalendarEventWriting: AnyObject {
    var authorization: CalendarAccessState { get }
    var hasDefaultCalendarForNewEvents: Bool { get }
    func requestWriteOnlyAccess() async throws -> Bool
    func save(_ draft: CalendarEventDraft) throws
}

@MainActor
@available(macOS 14.0, *)
private final class EventKitCalendarWriter: CalendarEventWriting {
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

    var hasDefaultCalendarForNewEvents: Bool { eventStore.defaultCalendarForNewEvents != nil }

    func requestWriteOnlyAccess() async throws -> Bool {
        try await withCheckedThrowingContinuation { continuation in
            eventStore.requestWriteOnlyAccessToEvents { granted, error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume(returning: granted) }
            }
        }
    }

    func save(_ draft: CalendarEventDraft) throws {
        guard let calendar = eventStore.defaultCalendarForNewEvents else {
            throw CalendarEventCreationError.defaultCalendarUnavailable
        }
        let event = EKEvent(eventStore: eventStore)
        event.calendar = calendar
        event.title = draft.title.trimmingCharacters(in: .whitespacesAndNewlines)
        event.startDate = draft.startDate
        event.endDate = draft.endDate
        event.location = draft.location?.nilIfBlank
        event.notes = draft.notes?.nilIfBlank
        try eventStore.save(event, span: .thisEvent, commit: true)
    }
}

private extension String {
    var nilIfBlank: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}

@MainActor
@Observable
@available(macOS 14.0, *)
public final class CalendarEventCreationService {
    private let writer: any CalendarEventWriting
    public private(set) var status = "填写事件后检查日历创建权限；检查不会创建事件。"
    public private(set) var isReadyToCreate = false
    public private(set) var hasCreatedEvent = false

    public init() {
        writer = EventKitCalendarWriter()
    }

    init(writer: any CalendarEventWriting) {
        self.writer = writer
    }

    public func invalidateReadiness() {
        isReadyToCreate = false
    }

    /// Requests write access only after the user explicitly starts the creation flow.
    /// This method never saves an event.
    public func prepareForEventCreation() async -> Bool {
        isReadyToCreate = false
        do {
            switch writer.authorization {
            case .fullAccess, .writeOnly:
                break
            case .notDetermined:
                guard try await writer.requestWriteOnlyAccess() else {
                    status = "尚未获得日历创建授权。"
                    return false
                }
            case .denied, .restricted:
                status = "没有日历创建权限；可在 macOS 系统设置的隐私与安全性中修改。"
                return false
            }
            guard writer.hasDefaultCalendarForNewEvents else {
                status = "macOS 当前没有可用于新事件的默认日历。"
                return false
            }
            isReadyToCreate = true
            status = "可以创建事件。确认前不会写入日历。"
            return true
        } catch {
            status = "无法检查日历创建权限。"
            return false
        }
    }

    /// Call only after the UI has shown the exact event and the user has confirmed it.
    public func createApprovedEvent(_ draft: CalendarEventDraft) throws {
        guard !hasCreatedEvent else { throw CalendarEventCreationError.eventAlreadyCreated }
        guard isReadyToCreate,
              writer.authorization == .fullAccess || writer.authorization == .writeOnly
        else { throw CalendarEventCreationError.authorizationRequired }
        let normalized = try Self.validatedDraft(draft)
        guard writer.hasDefaultCalendarForNewEvents else {
            throw CalendarEventCreationError.defaultCalendarUnavailable
        }
        try writer.save(normalized)
        hasCreatedEvent = true
        status = "事件已创建。"
    }

    public static func validatedDraft(_ draft: CalendarEventDraft) throws -> CalendarEventDraft {
        let title = draft.title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, title.count <= 200 else { throw CalendarEventCreationError.invalidTitle }
        guard draft.endDate > draft.startDate else { throw CalendarEventCreationError.invalidDateRange }
        let location = draft.location?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        let notes = draft.notes?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfBlank
        guard (location?.count ?? 0) <= 200, (notes?.count ?? 0) <= 2_000 else {
            throw CalendarEventCreationError.fieldTooLong
        }
        return CalendarEventDraft(
            title: title, startDate: draft.startDate, endDate: draft.endDate,
            location: location, notes: notes
        )
    }
}
