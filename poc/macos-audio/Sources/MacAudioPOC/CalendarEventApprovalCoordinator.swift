import Foundation

public protocol CalendarEventAuditRecording: Sendable {
    func recordCalendarEventAudit(
        traceID: UUID,
        resourceID: UUID,
        decision: CalendarEventAuditDecision,
        reason: CalendarEventAuditReason
    ) async throws
}

public enum CalendarEventApprovalOutcome: Equatable, Sendable {
    case invalidEventDetails
    case blockedByAudit
    case eventCreationFailed(auditRecorded: Bool)
    case eventCreated(auditRecorded: Bool)
}

@MainActor
@available(macOS 14.0, *)
public final class CalendarEventApprovalCoordinator {
    private let audit: any CalendarEventAuditRecording
    private let eventCreation: CalendarEventCreationService

    public init(audit: any CalendarEventAuditRecording, eventCreation: CalendarEventCreationService) {
        self.audit = audit
        self.eventCreation = eventCreation
    }

    /// Call only from the explicit per-event confirmation action.
    public func createAfterExplicitApproval(
        _ draft: CalendarEventDraft,
        traceID: UUID = UUID(),
        resourceID: UUID = UUID()
    ) async -> CalendarEventApprovalOutcome {
        do {
            _ = try CalendarEventCreationService.validatedDraft(draft)
        } catch {
            return .invalidEventDetails
        }

        do {
            try await audit.recordCalendarEventAudit(
                traceID: traceID, resourceID: resourceID,
                decision: .attempted, reason: .userApproved
            )
        } catch {
            eventCreation.invalidateReadiness()
            return .blockedByAudit
        }

        do {
            try eventCreation.createApprovedEvent(draft)
        } catch {
            let auditRecorded: Bool
            do {
                try await audit.recordCalendarEventAudit(
                    traceID: traceID, resourceID: resourceID,
                    decision: .failed, reason: .eventCreationFailed
                )
                auditRecorded = true
            } catch {
                auditRecorded = false
            }
            eventCreation.invalidateReadiness()
            return .eventCreationFailed(auditRecorded: auditRecorded)
        }

        let auditRecorded: Bool
        do {
            try await audit.recordCalendarEventAudit(
                traceID: traceID, resourceID: resourceID,
                decision: .succeeded, reason: .eventCreated
            )
            auditRecorded = true
        } catch {
            auditRecorded = false
        }
        eventCreation.invalidateReadiness()
        return .eventCreated(auditRecorded: auditRecorded)
    }
}
