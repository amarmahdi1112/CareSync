import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  PlusIcon,
  ShieldExclamationIcon,
  TrashIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import {
  ActionButton,
  Eyebrow,
  IconButton,
} from "../../components/ui/Primitives";
import {
  facilityDateTimeInputValue,
  facilityDateTimeToIso,
} from "../daily-care/careModel";
import {
  OperationDialog,
  OperationDialogActions,
  OperationDialogHeader,
  OperationForm,
  OperationFormGrid,
} from "../safety-operations/OperationDialog";
import {
  OperationField,
  OperationNotice,
} from "../safety-operations/OperationStyles";
import {
  createIncidentOperationId,
  fetchIncidentHistory,
  type IncidentAuditEvent,
  type ContactedAuthority,
  type IncidentAssessment,
  type IncidentCategory,
  type IncidentRecord,
  type IncidentSeverity,
  type MedicalAttention,
  type ParentNotificationStatus,
  type SubmissionChannel,
} from "./incidentApi";
import { formatCareTime } from "../daily-care/careModel";

const CheckGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  grid-column: 1 / -1;

  > span {
    grid-column: 1 / -1;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    font-weight: 650;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }

  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;

const Check = styled.label`
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 9px 10px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px 4px 10px 4px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  font-size: 0.72rem;

  input {
    width: 20px;
    height: 20px;
    accent-color: ${({ theme }) => theme.color.cyan};
  }
`;

const StaffList = styled.div`
  display: grid;
  gap: 7px;
  grid-column: 1 / -1;
  > span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    font-weight: 650;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
`;

const StaffRow = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px;
  gap: 7px;
  input {
    width: 100%;
    min-height: 44px;
    padding: 0 11px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px 5px 11px 5px;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
  }
`;

export interface IncidentAttendanceOption {
  attendanceDayId: string;
  childId: string;
  childName: string;
}

export interface IncidentDraft {
  attendanceDayId: string | null;
  occurredAt: string;
  category: IncidentCategory;
  severity: IncidentSeverity;
  summary: string;
  immediateActions: string;
  medicalAttention: MedicalAttention;
  parentNotificationStatus: ParentNotificationStatus;
  parentNotifiedAt: string | null;
  parentNotificationNotes: string | null;
  authoritiesContacted: ContactedAuthority[];
  staffPresent: string[];
  updateReason: string | null;
  clientOperationId: string;
}

const authorityOptions: { value: ContactedAuthority; label: string }[] = [
  { value: "emergency_services", label: "Emergency services" },
  { value: "police", label: "Police" },
  { value: "child_intervention", label: "Child Intervention" },
  { value: "child_care_connect", label: "Child Care Connect" },
  { value: "other", label: "Other authority" },
];

export function IncidentDraftDialog({
  incident,
  roomName,
  attendanceOptions,
  timeZone,
  busy,
  onClose,
  onSave,
}: {
  incident?: IncidentRecord;
  roomName: string;
  attendanceOptions: IncidentAttendanceOption[];
  timeZone: string;
  busy: boolean;
  onClose: () => void;
  onSave: (draft: IncidentDraft) => Promise<void>;
}) {
  const [attendanceDayId, setAttendanceDayId] = useState(
    incident?.attendance_day_id || "",
  );
  const [occurredInput, setOccurredInput] = useState(() =>
    facilityDateTimeInputValue(
      incident?.occurred_at || new Date().toISOString(),
      timeZone,
    ),
  );
  const [category, setCategory] = useState<IncidentCategory>(
    incident?.category || "injury",
  );
  const [severity, setSeverity] = useState<IncidentSeverity>(
    incident?.severity || "minor",
  );
  const [summary, setSummary] = useState(incident?.summary || "");
  const [immediateActions, setImmediateActions] = useState(
    incident?.immediate_actions || "",
  );
  const [medicalAttention, setMedicalAttention] = useState<MedicalAttention>(
    incident?.medical_attention || "none",
  );
  const [parentStatus, setParentStatus] = useState<ParentNotificationStatus>(
    incident?.parent_notification_status || "pending",
  );
  const [parentTime, setParentTime] = useState(() =>
    incident?.parent_notified_at
      ? facilityDateTimeInputValue(incident.parent_notified_at, timeZone)
      : facilityDateTimeInputValue(new Date().toISOString(), timeZone),
  );
  const [parentNotes, setParentNotes] = useState(
    incident?.parent_notification_notes || "",
  );
  const [authorities, setAuthorities] = useState<
    ReadonlySet<ContactedAuthority>
  >(() => new Set(incident?.authorities_contacted || []));
  const [staff, setStaff] = useState<string[]>(
    incident?.staff_present.length ? incident.staff_present : [""],
  );
  const [updateReason, setUpdateReason] = useState("");
  const [clientOperationId] = useState(createIncidentOperationId);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const staffPresent = [
        ...new Set(staff.map((name) => name.trim()).filter(Boolean)),
      ];
      if (staffPresent.length === 0)
        throw new Error(
          "Record at least one staff member or individual who was present.",
        );
      if (parentStatus === "notified" && !parentTime)
        throw new Error("Record when the parent was notified.");
      if (
        (parentStatus === "notified" || parentStatus === "unable_to_reach") &&
        parentNotes.trim().length < 3
      )
        throw new Error("Record factual parent-contact details.");
      await onSave({
        attendanceDayId: attendanceDayId || null,
        occurredAt: facilityDateTimeToIso(occurredInput, timeZone),
        category,
        severity,
        summary: summary.trim(),
        immediateActions: immediateActions.trim(),
        medicalAttention,
        parentNotificationStatus: parentStatus,
        parentNotifiedAt:
          parentStatus === "notified"
            ? facilityDateTimeToIso(parentTime, timeZone)
            : null,
        parentNotificationNotes:
          parentStatus === "notified" || parentStatus === "unable_to_reach"
            ? parentNotes.trim()
            : null,
        authoritiesContacted: [...authorities],
        staffPresent,
        updateReason: incident ? updateReason.trim() : null,
        clientOperationId,
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The internal incident draft could not be saved.",
      );
    }
  };

  const critical =
    severity === "critical" ||
    category === "missing_child" ||
    category === "allegation";
  return (
    <OperationDialog
      busy={busy}
      onClose={onClose}
      labelId="incident-draft-title"
    >
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <IdentificationIcon width={14} /> Internal incident draft
          </Eyebrow>
          <h2 id="incident-draft-title">
            {incident
              ? "Edit factual incident draft."
              : "Start a factual incident draft."}
          </h2>
          <p>
            {roomName} · This saves inside CareSync only. It does not submit
            anything to Alberta or determine legal classification.
          </p>
        </div>
        <IconButton
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close incident draft"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        {critical && (
          <OperationNotice $error>
            <ShieldExclamationIcon />{" "}
            <span>
              <strong>Potentially critical working selection.</strong> Do not
              delay immediate safety action, emergency help, parent contact,
              Child Intervention, police, or Child Care Connect as applicable.{" "}
              <a
                href="https://www.alberta.ca/childcare-report-an-incident-concern-or-complaint"
                target="_blank"
                rel="noreferrer"
              >
                Review current Alberta incident guidance
              </a>
              {category === "allegation" && (
                <>
                  {" "}
                  and{" "}
                  <a
                    href="https://www.alberta.ca/report-child-abuse"
                    target="_blank"
                    rel="noreferrer"
                  >
                    current child-abuse reporting guidance
                  </a>
                </>
              )}
              .
            </span>
          </OperationNotice>
        )}
        <OperationFormGrid>
          <OperationField>
            <span>Child involved</span>
            <select
              value={attendanceDayId}
              onChange={(event) => setAttendanceDayId(event.target.value)}
            >
              <option value="">Room-wide or no child selected</option>
              {attendanceOptions.map((option) => (
                <option
                  key={option.attendanceDayId}
                  value={option.attendanceDayId}
                >
                  {option.childName}
                </option>
              ))}
            </select>
            <small>
              Only children with a verified attendance-day option are
              selectable.
            </small>
          </OperationField>
          <OperationField>
            <span>Facility date and time</span>
            <input
              required
              type="datetime-local"
              value={occurredInput}
              onChange={(event) => setOccurredInput(event.target.value)}
            />
            <small>{timeZone}</small>
          </OperationField>
          <OperationField>
            <span>Incident type</span>
            <select
              value={category}
              onChange={(event) =>
                setCategory(event.target.value as IncidentCategory)
              }
            >
              <option value="injury">Accident or injury</option>
              <option value="illness">Serious or unexpected illness</option>
              <option value="missing_child">Missing or lost child</option>
              <option value="unauthorized_release">
                Unauthorized removal or release
              </option>
              <option value="allegation">
                Allegation, including abuse or neglect
              </option>
              <option value="emergency">
                Emergency, evacuation, closure, or intruder
              </option>
              <option value="other">Other</option>
            </select>
          </OperationField>
          <OperationField>
            <span>Working severity</span>
            <select
              value={severity}
              onChange={(event) =>
                setSeverity(event.target.value as IncidentSeverity)
              }
            >
              <option value="minor">Minor — requires review</option>
              <option value="moderate">Moderate — requires review</option>
              <option value="serious">Serious — prompt review</option>
              <option value="critical">
                Critical — immediate action and review
              </option>
            </select>
            <small>A staff selection, not a legal determination.</small>
          </OperationField>
          <OperationField $wide>
            <span>Factual description</span>
            <textarea
              required
              minLength={10}
              maxLength={4000}
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="What was directly observed?"
            />
          </OperationField>
          <OperationField $wide>
            <span>Immediate actions taken</span>
            <textarea
              required
              minLength={3}
              maxLength={4000}
              value={immediateActions}
              onChange={(event) => setImmediateActions(event.target.value)}
              placeholder="Record actions already taken; this screen does not provide medical advice."
            />
          </OperationField>
          <OperationField>
            <span>Medical attention observed</span>
            <select
              value={medicalAttention}
              onChange={(event) =>
                setMedicalAttention(event.target.value as MedicalAttention)
              }
            >
              <option value="none">None recorded</option>
              <option value="first_aid">First aid</option>
              <option value="medical_practitioner">Medical practitioner</option>
              <option value="emergency_services">Emergency services</option>
            </select>
          </OperationField>
          <OperationField>
            <span>Parent contact status</span>
            <select
              value={parentStatus}
              onChange={(event) =>
                setParentStatus(event.target.value as ParentNotificationStatus)
              }
            >
              <option value="pending">Pending</option>
              <option value="notified">Successfully notified</option>
              <option value="unable_to_reach">
                Attempted, unable to reach
              </option>
              <option value="not_applicable">Not applicable</option>
            </select>
          </OperationField>
          {parentStatus === "notified" && (
            <OperationField>
              <span>Parent notified at</span>
              <input
                required
                type="datetime-local"
                value={parentTime}
                onChange={(event) => setParentTime(event.target.value)}
              />
            </OperationField>
          )}
          {(parentStatus === "notified" ||
            parentStatus === "unable_to_reach") && (
            <OperationField $wide>
              <span>Parent contact details</span>
              <textarea
                required
                maxLength={1500}
                value={parentNotes}
                onChange={(event) => setParentNotes(event.target.value)}
                placeholder="Who was contacted, method, and factual result"
              />
            </OperationField>
          )}
          <CheckGrid>
            <span>Authorities already contacted</span>
            {authorityOptions.map((option) => (
              <Check key={option.value}>
                <input
                  type="checkbox"
                  checked={authorities.has(option.value)}
                  onChange={(event) =>
                    setAuthorities((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(option.value);
                      else next.delete(option.value);
                      return next;
                    })
                  }
                />
                <span>{option.label}</span>
              </Check>
            ))}
          </CheckGrid>
          <StaffList>
            <span>Staff or individuals present</span>
            {staff.map((name, index) => (
              <StaffRow key={index}>
                <input
                  aria-label={`Person present ${index + 1}`}
                  required={index === 0}
                  maxLength={200}
                  value={name}
                  onChange={(event) =>
                    setStaff((current) =>
                      current.map((value, valueIndex) =>
                        valueIndex === index ? event.target.value : value,
                      ),
                    )
                  }
                />
                <IconButton
                  type="button"
                  aria-label={`Remove person present ${index + 1}`}
                  disabled={staff.length === 1}
                  onClick={() =>
                    setStaff((current) =>
                      current.filter((_, valueIndex) => valueIndex !== index),
                    )
                  }
                >
                  <TrashIcon />
                </IconButton>
              </StaffRow>
            ))}
            <ActionButton
              type="button"
              onClick={() => setStaff((current) => [...current, ""])}
            >
              <PlusIcon /> Add person
            </ActionButton>
          </StaffList>
          {incident && (
            <OperationField $wide>
              <span>Required update reason</span>
              <textarea
                required
                minLength={3}
                maxLength={1000}
                value={updateReason}
                onChange={(event) => setUpdateReason(event.target.value)}
              />
              <small>
                The reason is retained in the incident audit history.
              </small>
            </OperationField>
          )}
        </OperationFormGrid>
        {error && (
          <OperationNotice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </OperationNotice>
        )}
        <OperationDialogActions>
          <ActionButton type="button" disabled={busy} onClick={onClose}>
            Cancel
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? (
              <>
                <ArrowPathIcon /> Saving…
              </>
            ) : (
              "Save internal draft"
            )}
          </ActionButton>
        </OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

export function IncidentSubmitReviewDialog({
  incident,
  busy,
  onClose,
  onSave,
}: {
  incident: IncidentRecord;
  busy: boolean;
  onClose: () => void;
  onSave: (clientOperationId: string) => Promise<void>;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [clientOperationId] = useState(createIncidentOperationId);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (!confirmed)
        throw new Error("Confirm the draft is ready for internal review.");
      await onSave(clientOperationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The draft could not be sent for internal review.",
      );
    }
  };
  return (
    <OperationDialog
      busy={busy}
      onClose={onClose}
      labelId="incident-review-title"
    >
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <CheckCircleIcon width={14} /> Internal review
          </Eyebrow>
          <h2 id="incident-review-title">
            Send this draft for internal review?
          </h2>
          <p>{incident.summary} · No external report is sent by this action.</p>
        </div>
        <IconButton
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close internal review confirmation"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        <Check>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>
            I reviewed the factual description, immediate actions, contact
            attempts, and people present.
          </span>
        </Check>
        {error && (
          <OperationNotice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </OperationNotice>
        )}
        <OperationDialogActions>
          <ActionButton type="button" disabled={busy} onClick={onClose}>
            Keep draft
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Moving to review…" : "Begin internal review"}
          </ActionButton>
        </OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

export function IncidentFinalizeDialog({
  incident,
  busy,
  onClose,
  onSave,
}: {
  incident: IncidentRecord;
  busy: boolean;
  onClose: () => void;
  onSave: (
    assessment: Exclude<IncidentAssessment, "unassessed">,
    reviewerNote: string,
    clientOperationId: string,
  ) => Promise<void>;
}) {
  const [assessment, setAssessment] =
    useState<Exclude<IncidentAssessment, "unassessed">>("not_reportable");
  const [reviewerNote, setReviewerNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [clientOperationId] = useState(createIncidentOperationId);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (reviewerNote.trim().length < 3)
        throw new Error("Record the human reviewer’s assessment note.");
      if (!confirmed)
        throw new Error(
          "Confirm that a responsible human reviewer made this internal assessment.",
        );
      await onSave(assessment, reviewerNote.trim(), clientOperationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The internal review could not be finalized.",
      );
    }
  };
  return (
    <OperationDialog
      busy={busy}
      onClose={onClose}
      labelId="incident-finalize-title"
    >
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <ShieldExclamationIcon width={14} /> Human reportability review
          </Eyebrow>
          <h2 id="incident-finalize-title">
            Finalize the internal assessment.
          </h2>
          <p>
            CareSync does not determine legal reportability. This selection must
            be made by a responsible reviewer using current Alberta guidance.
          </p>
        </div>
        <IconButton
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close finalization form"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        <OperationNotice $warning>
          <ExclamationTriangleIcon /> If unsure, confirm with Child Care
          Connect. Critical matters require immediate action and applicable
          external contact; this screen must never delay response.
        </OperationNotice>
        <OperationField>
          <span>Human reviewer assessment</span>
          <select
            value={assessment}
            onChange={(event) =>
              setAssessment(
                event.target.value as Exclude<IncidentAssessment, "unassessed">,
              )
            }
          >
            <option value="not_reportable">
              Internally assessed as not reportable
            </option>
            <option value="other_reportable">Other reportable incident</option>
            <option value="critical">Critical incident</option>
          </select>
        </OperationField>
        <OperationField>
          <span>Required reviewer note</span>
          <textarea
            required
            minLength={3}
            maxLength={3000}
            value={reviewerNote}
            onChange={(event) => setReviewerNote(event.target.value)}
          />
        </OperationField>
        <Check>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>
            I am recording a human review against current guidance. I understand
            CareSync will not submit the report externally.
          </span>
        </Check>
        {error && (
          <OperationNotice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </OperationNotice>
        )}
        <OperationDialogActions>
          <ActionButton type="button" disabled={busy} onClick={onClose}>
            Continue review
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Finalizing…" : "Finalize internal assessment"}
          </ActionButton>
        </OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

export interface ExternalReportDraft {
  reportedAt: string;
  confirmationReference: string;
  submissionChannel: SubmissionChannel;
  submittedByName: string;
  clientOperationId: string;
}

export function ExternalReportDialog({
  incident,
  timeZone,
  busy,
  onClose,
  onSave,
}: {
  incident: IncidentRecord;
  timeZone: string;
  busy: boolean;
  onClose: () => void;
  onSave: (draft: ExternalReportDraft) => Promise<void>;
}) {
  const [reportedInput, setReportedInput] = useState(() =>
    facilityDateTimeInputValue(new Date().toISOString(), timeZone),
  );
  const [reference, setReference] = useState("");
  const [channel, setChannel] = useState<SubmissionChannel>(
    incident.reportability_assessment === "critical"
      ? "child_care_connect_then_portal"
      : "alberta_licensing_portal",
  );
  const [submittedBy, setSubmittedBy] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [clientOperationId] = useState(createIncidentOperationId);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (!confirmed)
        throw new Error(
          "Confirm that an external submission actually occurred outside CareSync.",
        );
      await onSave({
        reportedAt: facilityDateTimeToIso(reportedInput, timeZone),
        confirmationReference: reference.trim(),
        submissionChannel: channel,
        submittedByName: submittedBy.trim(),
        clientOperationId,
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The external confirmation could not be recorded.",
      );
    }
  };
  return (
    <OperationDialog
      busy={busy}
      onClose={onClose}
      labelId="external-report-title"
    >
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <IdentificationIcon width={14} /> Manual external confirmation
          </Eyebrow>
          <h2 id="external-report-title">
            Record a completed external action.
          </h2>
          <p>
            This form only records evidence from an action a person completed
            outside CareSync. It does not contact Alberta or submit a portal
            report.
          </p>
        </div>
        <IconButton
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close external confirmation form"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        <OperationFormGrid>
          <OperationField>
            <span>External action completed at</span>
            <input
              required
              type="datetime-local"
              value={reportedInput}
              onChange={(event) => setReportedInput(event.target.value)}
            />
            <small>{timeZone}</small>
          </OperationField>
          <OperationField>
            <span>External channel used</span>
            <select
              value={channel}
              onChange={(event) =>
                setChannel(event.target.value as SubmissionChannel)
              }
            >
              <option value="alberta_licensing_portal">
                Alberta Licensing Portal
              </option>
              <option value="child_care_connect_then_portal">
                Child Care Connect, then portal
              </option>
            </select>
          </OperationField>
          <OperationField>
            <span>Confirmation or reference</span>
            <input
              required
              minLength={3}
              maxLength={500}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </OperationField>
          <OperationField>
            <span>Person who submitted externally</span>
            <input
              required
              minLength={2}
              maxLength={200}
              value={submittedBy}
              onChange={(event) => setSubmittedBy(event.target.value)}
            />
          </OperationField>
        </OperationFormGrid>
        <Check>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>
            I confirm this external action already occurred and the reference
            above is evidence of it.
          </span>
        </Check>
        {error && (
          <OperationNotice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </OperationNotice>
        )}
        <OperationDialogActions>
          <ActionButton type="button" disabled={busy} onClick={onClose}>
            Cancel
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Recording…" : "Record external confirmation"}
          </ActionButton>
        </OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

export function ReturnIncidentDialog({
  incident,
  busy,
  onClose,
  onSave,
}: {
  incident: IncidentRecord;
  busy: boolean;
  onClose: () => void;
  onSave: (reason: string, clientOperationId: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [clientOperationId] = useState(createIncidentOperationId);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      if (reason.trim().length < 3)
        throw new Error("Record why the incident is returning to draft.");
      await onSave(reason.trim(), clientOperationId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The incident could not return to draft.",
      );
    }
  };
  return (
    <OperationDialog
      busy={busy}
      onClose={onClose}
      labelId="incident-return-title"
    >
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <ExclamationTriangleIcon width={14} /> Review revision
          </Eyebrow>
          <h2 id="incident-return-title">Return this incident to draft?</h2>
          <p>The reason is retained in the immutable audit history.</p>
        </div>
        <IconButton
          type="button"
          disabled={busy}
          onClick={onClose}
          aria-label="Close return-to-draft form"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      <OperationForm onSubmit={submit}>
        <OperationField>
          <span>Required review reason</span>
          <textarea
            required
            maxLength={1500}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </OperationField>
        {error && (
          <OperationNotice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </OperationNotice>
        )}
        <OperationDialogActions>
          <ActionButton type="button" disabled={busy} onClick={onClose}>
            Keep in review
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Returning…" : "Return to internal draft"}
          </ActionButton>
        </OperationDialogActions>
      </OperationForm>
    </OperationDialog>
  );
}

const HistoryList = styled.div`
  display: grid;
  gap: 8px;
`;
const HistoryRow = styled.div`
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr);
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  &::before {
    width: 7px;
    height: 7px;
    margin-top: 5px;
    border-radius: 50%;
    content: "";
    background: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    font-size: 0.76rem;
    text-transform: capitalize;
  }
  p {
    margin: 3px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.69rem;
    line-height: 1.5;
  }
`;

export function IncidentHistoryDialog({
  incident,
  onClose,
}: {
  incident: IncidentRecord;
  onClose: () => void;
}) {
  const [result, setResult] = useState<{
    events: IncidentAuditEvent[];
    loading: boolean;
    error: string;
  }>({ events: [], loading: true, error: "" });
  useEffect(() => {
    const controller = new AbortController();
    setResult({ events: [], loading: true, error: "" });
    fetchIncidentHistory(incident.id, controller.signal)
      .then((events) => {
        if (!controller.signal.aborted)
          setResult({ events, loading: false, error: "" });
      })
      .catch((caught) => {
        if (!controller.signal.aborted)
          setResult({
            events: [],
            loading: false,
            error:
              caught instanceof Error
                ? caught.message
                : "Incident history could not be loaded.",
          });
      });
    return () => controller.abort();
  }, [incident.id]);
  return (
    <OperationDialog onClose={onClose} labelId="incident-history-title">
      <OperationDialogHeader>
        <div>
          <Eyebrow>
            <IdentificationIcon width={14} /> Immutable incident history
          </Eyebrow>
          <h2 id="incident-history-title">Internal audit trail.</h2>
          <p>
            Every draft change and workflow transition remains attributed.
            External submission is never performed by CareSync.
          </p>
        </div>
        <IconButton
          type="button"
          onClick={onClose}
          aria-label="Close incident history"
        >
          <XMarkIcon />
        </IconButton>
      </OperationDialogHeader>
      {result.loading && (
        <OperationNotice role="status" aria-live="polite">
          <ArrowPathIcon /> Loading incident history…
        </OperationNotice>
      )}
      {result.error && (
        <OperationNotice $error role="alert">
          <ExclamationTriangleIcon /> {result.error}
        </OperationNotice>
      )}
      {!result.loading && !result.error && (
        <HistoryList>
          {result.events.map((event) => (
            <HistoryRow key={event.id}>
              <div>
                <strong>{event.event_type.replaceAll("_", " ")}</strong>
                <p>
                  {formatCareTime(
                    event.occurred_at,
                    incident.facility_timezone,
                  )}{" "}
                  {incident.facility_timezone} · {event.actor_name}
                  {event.reason ? ` · ${event.reason}` : ""}
                </p>
              </div>
            </HistoryRow>
          ))}
          {result.events.length === 0 && (
            <OperationNotice>No incident events were returned.</OperationNotice>
          )}
        </HistoryList>
      )}
    </OperationDialog>
  );
}
