import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  ArrowPathIcon,
  CheckIcon,
  ClipboardDocumentIcon,
  EnvelopeIcon,
  ExclamationTriangleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  KeyIcon,
  MagnifyingGlassIcon,
  NoSymbolIcon,
  PencilSquareIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UserPlusIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { useSession } from "../../auth/SessionContext";
import { ACCESS, hasPermission } from "../../auth/accessModel";
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  IconButton,
  StatusChip,
} from "../../components/ui/Primitives";
import {
  absoluteHandoffUrl,
  roomFacilityIds,
  validateStaffDraft,
} from "./staffModel";
import { staffApi } from "./staffApi";
import type {
  StaffInviteInput,
  StaffMember,
  StaffRole,
  StaffRoom,
  StaffWorkspace,
} from "./types";

const Page = styled.div`
  display: grid;
  gap: 22px;
  padding-bottom: 40px;
`;
const Header = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  h1 {
    margin: 8px 0 6px;
    font-family: "CareSync Display", sans-serif;
    font-size: clamp(1.65rem, 3vw, 2.45rem);
    font-weight: 600;
    letter-spacing: -0.05em;
  }
  p {
    max-width: 68ch;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.82rem;
    line-height: 1.7;
  }
  @media (max-width: 760px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Metrics = styled.section`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  @media (max-width: 900px) {
    grid-template-columns: repeat(2, 1fr);
  }
  @media (max-width: 480px) {
    grid-template-columns: 1fr;
  }
`;
const Metric = styled(GlassPanel)`
  padding: 16px 18px;
  span {
    display: block;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  strong {
    display: block;
    margin-top: 8px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.7rem;
    font-weight: 600;
  }
`;
const Toolbar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  @media (max-width: 680px) {
    align-items: stretch;
    flex-direction: column;
  }
`;
const Search = styled.label`
  display: flex;
  min-height: 44px;
  flex: 1;
  align-items: center;
  gap: 9px;
  padding: 0 13px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 7px 13px 7px 13px;
  background: ${({ theme }) => theme.color.control};
  svg {
    width: 18px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  input {
    width: 100%;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font: inherit;
  }
`;
const Select = styled.select`
  min-height: 44px;
  padding: 0 36px 0 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 7px 13px 7px 13px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.control};
`;
const Section = styled.section`
  display: grid;
  gap: 12px;
`;
const SectionHead = styled.div`
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.12rem;
    font-weight: 600;
  }
  p {
    margin: 4px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.76rem;
  }
`;
const Directory = styled(GlassPanel)`
  display: grid;
  overflow: hidden;
`;
const Row = styled.article`
  display: grid;
  grid-template-columns: minmax(220px, 1.4fr) minmax(130px, 0.7fr) minmax(
      190px,
      1fr
    ) auto;
  align-items: center;
  gap: 18px;
  min-height: 82px;
  padding: 14px 18px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  &:last-child {
    border-bottom: 0;
  }
  @media (max-width: 900px) {
    grid-template-columns: 1fr auto;
    > div:nth-child(2),
    > div:nth-child(3) {
      grid-column: 1/-1;
    }
  }
`;
const Identity = styled.div`
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
`;
const Avatar = styled.span`
  display: grid;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 9px 14px 9px 14px;
  color: ${({ theme }) => theme.color.cyan};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-family: "CareSync Display", sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
`;
const Copy = styled.div`
  min-width: 0;
  strong,
  small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  strong {
    font-size: 0.84rem;
    font-weight: 600;
  }
  small {
    margin-top: 3px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
  }
`;
const Scope = styled.div`
  strong,
  small {
    display: block;
  }
  strong {
    font-size: 0.78rem;
    font-weight: 600;
  }
  small {
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
  }
`;
const RowActions = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: 6px;
`;
const MemberDetail = styled.div`
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px 13px 8px 13px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  dl {
    min-width: 0;
    margin: 0;
  }
  dt {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
  }
  dd {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.74rem;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
  @media (max-width: 760px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  @media (max-width: 460px) {
    grid-template-columns: 1fr;
  }
`;
const Empty = styled(GlassPanel)`
  padding: 44px 24px;
  text-align: center;
  svg {
    width: 40px;
    color: ${({ theme }) => theme.color.textMuted};
  }
  h3 {
    margin: 12px 0 6px;
    font-size: 1rem;
    font-weight: 600;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.78rem;
  }
`;
const Notice = styled.div<{ $error?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid
    ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.borderStrong)};
  border-radius: 8px 14px 8px 14px;
  color: ${({ $error, theme }) => ($error ? theme.color.coral : theme.color.textSoft)};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.78rem;
  line-height: 1.55;
  svg {
    width: 18px;
    flex: 0 0 auto;
  }
`;
const Gate = styled(GlassPanel)`
  padding: 54px 24px;
  text-align: center;
  svg {
    width: 42px;
    color: ${({ theme }) => theme.color.cyan};
  }
  h2 {
    margin: 12px 0 6px;
    font-size: 1.05rem;
    font-weight: 600;
  }
  p {
    margin: 0 auto 18px;
    max-width: 50ch;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.78rem;
  }
`;

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 500;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(4, 10, 20, 0.72);
`;
const Dialog = styled(GlassPanel)`
  width: min(660px, 100%);
  max-height: min(86vh, 820px);
  overflow: auto;
  padding: 22px;
`;
const DialogHead = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  h2 {
    margin: 7px 0 4px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.35rem;
    font-weight: 600;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.77rem;
    line-height: 1.6;
  }
`;
const Form = styled.form`
  display: grid;
  gap: 16px;
`;
const Grid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  @media (max-width: 560px) {
    grid-template-columns: 1fr;
  }
`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => ($wide ? "1/-1" : "auto")};
  gap: 7px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: 0.75rem;
  font-weight: 600;
  input,
  select {
    min-height: 44px;
    padding: 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 7px 12px 7px 12px;
    outline: none;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    &:focus {
      border-color: ${({ theme }) => theme.color.cyan};
    }
  }
`;
const Assignment = styled.fieldset`
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 9px 15px 9px 15px;
  legend {
    padding: 0 8px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: 0.75rem;
    font-weight: 600;
  }
`;
const FacilityGroup = styled.div`
  display: grid;
  gap: 8px;
  padding: 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 8px 12px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  > strong {
    font-size: 0.78rem;
    font-weight: 600;
  }
`;
const Choices = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;
const Choice = styled.label`
  display: flex;
  min-height: 42px;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 7px 11px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.control};
  font-size: 0.75rem;
  cursor: pointer;
  input {
    accent-color: ${({ theme }) => theme.color.cyan};
  }
`;
const FormActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
`;
const Secret = styled.div`
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 9px 14px;
  background: ${({ theme }) => theme.color.control};
  code {
    display: block;
    overflow-wrap: anywhere;
    color: ${({ theme }) => theme.color.cyan};
    font-size: 0.75rem;
    line-height: 1.6;
  }
`;

function initials(first: string, last: string) {
  return `${first[0] || ""}${last[0] || ""}`.toUpperCase();
}
function statusTone(status: string): "success" | "warning" | "neutral" {
  return status === "active"
    ? "success"
    : status === "pending"
      ? "warning"
      : "neutral";
}

function Modal({
  titleId,
  onClose,
  busy,
  children,
}: {
  titleId: string;
  onClose: () => void;
  busy?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() =>
      ref.current?.querySelector<HTMLElement>("input,select,button")?.focus(),
    );
    return () => {
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <Overlay
      onMouseDown={(event) =>
        event.target === event.currentTarget && !busy && onClose()
      }
    >
      <Dialog
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (event.key === "Escape" && !busy) onClose();
          if (event.key !== "Tab") return;
          const focusable = [
            ...(ref.current?.querySelectorAll<HTMLElement>(
              "button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]",
            ) || []),
          ];
          if (!focusable.length) return;
          if (event.shiftKey && document.activeElement === focusable[0]) {
            event.preventDefault();
            focusable.at(-1)?.focus();
          } else if (
            !event.shiftKey &&
            document.activeElement === focusable.at(-1)
          ) {
            event.preventDefault();
            focusable[0].focus();
          }
        }}
      >
        {children}
      </Dialog>
    </Overlay>
  );
}

function RoomChoices({
  rooms,
  workspace,
  selected,
  onChange,
}: {
  rooms: StaffRoom[];
  workspace: StaffWorkspace;
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const selectedSet = new Set(selected);
  const activeFacilities = workspace.facilities.filter(
    (facility) =>
      facility.status === "active" &&
      rooms.some((room) => room.facility_id === facility.id && room.is_active),
  );
  return (
    <Assignment>
      <legend>Assigned active rooms</legend>
      {activeFacilities.map((facility) => (
        <FacilityGroup key={facility.id}>
          <strong>{facility.name}</strong>
          <Choices>
            {rooms
              .filter(
                (room) => room.facility_id === facility.id && room.is_active,
              )
              .map((room) => (
                <Choice key={room.id}>
                  <input
                    type="checkbox"
                    checked={selectedSet.has(room.id)}
                    onChange={(event) =>
                      onChange(
                        event.target.checked
                          ? [...selected, room.id]
                          : selected.filter((id) => id !== room.id),
                      )
                    }
                  />{" "}
                  {room.name}
                </Choice>
              ))}
          </Choices>
        </FacilityGroup>
      ))}
    </Assignment>
  );
}

const blankInvite = (): StaffInviteInput => ({
  email: "",
  first_name: "",
  last_name: "",
  role_id: "",
  assigned_facility_ids: [],
  assigned_room_ids: [],
});

type Confirmation =
  | { kind: "revoke"; id: string; name: string }
  | { kind: "suspend"; member: StaffMember };

export default function StaffPage() {
  const session = useSession();
  const organizationId = session.organization?.id || "";
  const canManageAll = hasPermission(session.user, ACCESS.staffManage);
  const canManageEducators =
    canManageAll || hasPermission(session.user, ACCESS.staffManageEducators);
  const [workspace, setWorkspace] = useState<StaffWorkspace | null>(null);
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [detailMemberId, setDetailMemberId] = useState("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editMember, setEditMember] = useState<StaffMember | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [secret, setSecret] = useState<{
    kind: "activation" | "reset";
    url: string;
    name: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");

  const loadStaff = useCallback(async (signal?: AbortSignal) => {
    if (!organizationId || !canManageEducators) return;
    setPhase("loading");
    setError("");
    try { const value = await staffApi.workspace(organizationId, signal); if (!signal?.aborted) { setWorkspace(value); setPhase("ready"); } }
    catch (caught) { if (!signal?.aborted) { setError(caught instanceof Error ? caught.message : "Staff access could not be loaded."); setPhase("error"); } throw caught; }
  }, [canManageEducators, organizationId]);
  useEffect(() => {
    const controller = new AbortController();
    void loadStaff(controller.signal).catch(() => undefined);
    return () => controller.abort();
  }, [loadStaff, revision]);
  useRealtimeRefresh({ scope: 'staff', organizationId, enabled: canManageEducators, eventPrefixes: ['staff.', 'hire.', 'assignment.', 'candidate.certification', 'candidate.provision'], entityTypes: featureIntegrationManifest.staff.realtimeEntities, refresh: async () => loadStaff() });

  const manageableMembers = useMemo(
    () =>
      (workspace?.members || []).filter(
        (member) => canManageAll || member.role.key === "educator",
      ),
    [canManageAll, workspace?.members],
  );
  const visibleMembers = useMemo(
    () =>
      manageableMembers.filter((member) => {
        const query = search.trim().toLowerCase();
        return (
          (!query ||
            `${member.first_name} ${member.last_name} ${member.email} ${member.role.name}`
              .toLowerCase()
              .includes(query)) &&
          (filter === "all" || member.membership_status === filter)
        );
      }),
    [filter, manageableMembers, search],
  );
  const pending = (workspace?.invitations || []).filter(
    (invite) =>
      invite.status === "pending" &&
      (canManageAll || invite.role.key === "educator"),
  );
  const assignableRoles = (workspace?.roles || []).filter(
    (role) => role.key !== "owner" && (canManageAll || role.key === "educator"),
  );
  const roomNames = (ids: string[]) => {
    const names = (workspace?.rooms || [])
      .filter((room) => ids.includes(room.id))
      .map((room) => room.name);
    return names.length
      ? `${names.slice(0, 2).join(", ")}${names.length > 2 ? ` +${names.length - 2}` : ""}`
      : "Organization-wide";
  };
  const fullRoomNames = (ids: string[]) =>
    (workspace?.rooms || [])
      .filter((room) => ids.includes(room.id))
      .map((room) => room.name)
      .join(", ") || "No room assignment";
  const facilityNames = (ids: string[]) =>
    (workspace?.facilities || [])
      .filter((facility) => ids.includes(facility.id))
      .map((facility) => facility.name)
      .join(", ") || "No facility assignment";
  const refresh = (message?: string) => {
    if (message) setNotice(message);
    setRevision((value) => value + 1);
  };

  const regenerate = async (id: string, name: string) => {
    setBusy(id);
    setError("");
    try {
      const result = await staffApi.regenerate(id);
      setSecret({
        kind: "activation",
        url: absoluteHandoffUrl(result.activation_url),
        name,
      });
      setCopied(false);
      refresh(
        "A new activation link was created. The previous link no longer works.",
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The activation link could not be regenerated.",
      );
    } finally {
      setBusy("");
    }
  };
  const revoke = async (id: string) => {
    setBusy(id);
    setError("");
    try {
      await staffApi.revoke(id);
      setConfirmation(null);
      refresh("Invitation revoked.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The invitation could not be revoked.",
      );
    } finally {
      setBusy("");
    }
  };
  const changeStatus = async (
    member: StaffMember,
    membership_status: "active" | "suspended",
  ) => {
    setBusy(member.membership_id);
    setError("");
    try {
      await staffApi.updateMember(member.membership_id, {
        role_id: member.role.id,
        assigned_facility_ids: member.assigned_facility_ids,
        assigned_room_ids: member.assigned_room_ids,
        membership_status,
      });
      setConfirmation(null);
      refresh(`${member.first_name} is now ${membership_status}.`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Staff access could not be changed.",
      );
    } finally {
      setBusy("");
    }
  };
  const resetPassword = async (member: StaffMember) => {
    setBusy(member.membership_id);
    setError("");
    try {
      const result = await staffApi.passwordReset(member.membership_id);
      setSecret({
        kind: "reset",
        url: absoluteHandoffUrl(result.reset_url),
        name: `${member.first_name} ${member.last_name}`,
      });
      setCopied(false);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "A password reset link could not be created.",
      );
    } finally {
      setBusy("");
    }
  };

  if (!canManageEducators)
    return (
      <Page>
        <Gate $accent="amber">
          <ShieldCheckIcon />
          <h2>Staff access is owner-managed.</h2>
          <p>
            Your account does not have permission to manage staff identities or
            room assignments.
          </p>
        </Gate>
      </Page>
    );

  return (
    <Page>
      <Header>
        <div>
          <Eyebrow>
            <ShieldCheckIcon width={14} /> Identity · least privilege
          </Eyebrow>
          <h1>Staff & access.</h1>
          <p>
            Invite educators, assign only the rooms they work in, and suspend
            access without deleting the audit trail.
          </p>
        </div>
        <ActionButton
          type="button"
          $variant="primary"
          onClick={() => setInviteOpen(true)}
          disabled={!workspace || !assignableRoles.length}
        >
          <UserPlusIcon /> Invite staff
        </ActionButton>
      </Header>
      {notice && (
        <Notice role="status" aria-live="polite">
          <CheckIcon /> {notice}
        </Notice>
      )}
      {error && phase !== "error" && (
        <Notice $error role="alert">
          <ExclamationTriangleIcon /> {error}
        </Notice>
      )}
      {phase === "loading" && (
        <Gate $accent="cyan" aria-busy="true">
          <ArrowPathIcon />
          <h2>Loading the staff directory.</h2>
          <p>
            CareSync is verifying roles, facilities, and room assignments before
            showing access controls.
          </p>
        </Gate>
      )}
      {phase === "error" && (
        <Gate $accent="amber">
          <ExclamationTriangleIcon />
          <h2>Staff access stayed locked.</h2>
          <p>{error}</p>
          <ActionButton onClick={() => setRevision((value) => value + 1)}>
            <ArrowPathIcon /> Try again
          </ActionButton>
        </Gate>
      )}
      {phase === "ready" && workspace && (
        <>
          <Metrics aria-label="Staff access summary">
            <Metric $accent="cyan">
              <span>Active staff</span>
              <strong>
                {
                  manageableMembers.filter(
                    (item) => item.membership_status === "active",
                  ).length
                }
              </strong>
            </Metric>
            <Metric $accent="amber">
              <span>Pending invites</span>
              <strong>{pending.length}</strong>
            </Metric>
            <Metric $accent="plasma">
              <span>Educators</span>
              <strong>
                {
                  manageableMembers.filter(
                    (item) => item.role.key === "educator",
                  ).length
                }
              </strong>
            </Metric>
            <Metric $accent="cyan">
              <span>Active rooms</span>
              <strong>
                {workspace.rooms.filter((item) => item.is_active).length}
              </strong>
            </Metric>
          </Metrics>
          <Toolbar $accent="plasma">
            <Search>
              <MagnifyingGlassIcon />
              <input
                type="search"
                aria-label="Search staff"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search staff or email…"
              />
            </Search>
            <Select
              aria-label="Filter staff status"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </Select>
          </Toolbar>
          <Section>
            <SectionHead>
              <div>
                <h2>Team directory</h2>
                <p>
                  {visibleMembers.length} member
                  {visibleMembers.length === 1 ? "" : "s"} available to manage.
                </p>
              </div>
            </SectionHead>
            {visibleMembers.length ? (
              <Directory $accent="cyan">
                {visibleMembers.map((member) => {
                  const immutableOwner = member.role.key === "owner";
                  const expanded = detailMemberId === member.membership_id;
                  return (
                    <Row key={member.membership_id}>
                      <Identity>
                        <Avatar>
                          {initials(member.first_name, member.last_name)}
                        </Avatar>
                        <Copy>
                          <strong>
                            {member.first_name} {member.last_name}
                          </strong>
                          <small>{member.email}</small>
                        </Copy>
                      </Identity>
                      <div>
                        <StatusChip
                          $tone={statusTone(member.membership_status)}
                        >
                          {member.membership_status}
                        </StatusChip>
                        <Copy>
                          <small>{member.role.name}</small>
                        </Copy>
                      </div>
                      <Scope>
                        <strong>
                          {member.assigned_room_ids.length} assigned room
                          {member.assigned_room_ids.length === 1 ? "" : "s"}
                        </strong>
                        <small>{roomNames(member.assigned_room_ids)}</small>
                      </Scope>
                      <RowActions>
                        <IconButton
                          type="button"
                          onClick={() =>
                            setDetailMemberId(
                              expanded ? "" : member.membership_id,
                            )
                          }
                          aria-expanded={expanded}
                          aria-label={`${expanded ? "Hide" : "Show"} access details for ${member.first_name} ${member.last_name}`}
                        >
                          {expanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
                        </IconButton>
                        {!immutableOwner && (
                          <IconButton
                            type="button"
                            onClick={() => setEditMember(member)}
                            aria-label={`Edit access for ${member.first_name} ${member.last_name}`}
                          >
                            <PencilSquareIcon />
                          </IconButton>
                        )}
                        {!immutableOwner &&
                          member.membership_status === "active" && (
                            <IconButton
                              type="button"
                              onClick={() => void resetPassword(member)}
                              disabled={busy === member.membership_id}
                              aria-label={`Create password reset link for ${member.first_name} ${member.last_name}`}
                            >
                              <KeyIcon />
                            </IconButton>
                          )}
                        {!immutableOwner &&
                          (member.membership_status === "active" ? (
                            <IconButton
                              type="button"
                              onClick={() =>
                                setConfirmation({ kind: "suspend", member })
                              }
                              disabled={busy === member.membership_id}
                              aria-label={`Suspend ${member.first_name} ${member.last_name}`}
                            >
                              <NoSymbolIcon />
                            </IconButton>
                          ) : (
                            <IconButton
                              type="button"
                              onClick={() =>
                                void changeStatus(member, "active")
                              }
                              disabled={busy === member.membership_id}
                              aria-label={`Reactivate ${member.first_name} ${member.last_name}`}
                            >
                              <ArrowPathIcon />
                            </IconButton>
                          ))}
                      </RowActions>
                      {expanded && (
                        <MemberDetail
                          aria-label={`Access details for ${member.first_name} ${member.last_name}`}
                        >
                          <dl>
                            <dt>Role</dt>
                            <dd>
                              {member.role.name}
                              <br />
                              {member.role.description ||
                                "Server-defined access role"}
                            </dd>
                          </dl>
                          <dl>
                            <dt>Facilities</dt>
                            <dd>
                              {facilityNames(member.assigned_facility_ids)}
                            </dd>
                          </dl>
                      <dl>
                        <dt>Rooms</dt>
                        <dd>{fullRoomNames(member.assigned_room_ids)}</dd>
                      </dl>
                      <dl>
                        <dt>Credential readiness</dt>
                        <dd>
                          {member.credential ? (
                            <>
                              {member.credential.ready ? 'Ready' : 'Needs attention'} ·{' '}
                              {member.credential.verification_status}
                              <br />
                              {member.credential.certification_type || 'Certification type unavailable'}
                              {member.credential.expiry_date
                                ? ` · expires ${new Date(member.credential.expiry_date).toLocaleDateString()}`
                                : ''}
                            </>
                          ) : (
                            'No credential on file'
                          )}
                        </dd>
                      </dl>
                      <dl>
                        <dt>Active assignments</dt>
                        <dd>
                          {member.active_assignments.length
                            ? member.active_assignments
                                .map(
                                  (assignment) =>
                                    `${assignment.facility_name}${assignment.room_name ? ` · ${assignment.room_name}` : ''}`,
                                )
                                .join(', ')
                            : 'No active assignment'}
                        </dd>
                      </dl>
                      <dl>
                        <dt>Current shift</dt>
                        <dd>
                          {member.current_shift
                            ? `${member.current_shift.status === 'open' ? 'Clocked in' : 'Closed'} · ${new Date(member.current_shift.clocked_in_at).toLocaleString()}${member.current_shift.clocked_out_at ? ` to ${new Date(member.current_shift.clocked_out_at).toLocaleString()}` : ''}`
                            : 'No open shift'}
                        </dd>
                      </dl>
                      <dl>
                            <dt>Membership timeline</dt>
                            <dd>
                              {member.joined_at
                                ? `Joined ${new Date(member.joined_at).toLocaleDateString()}`
                                : "Invitation not yet joined"}
                              <br />
                              Updated{" "}
                              {new Date(member.updated_at).toLocaleString()}
                            </dd>
                          </dl>
                        </MemberDetail>
                      )}
                    </Row>
                  );
                })}
              </Directory>
            ) : (
              <Empty $accent="plasma">
                <UserGroupIcon />
                <h3>No staff match this view.</h3>
                <p>Clear the filters or invite an educator.</p>
              </Empty>
            )}
          </Section>
          <Section>
            <SectionHead>
              <div>
                <h2>Pending invitations</h2>
                <p>
                  Activation secrets are shown only when created or regenerated.
                </p>
              </div>
            </SectionHead>
            {pending.length ? (
              <Directory $accent="amber">
                {pending.map((invite) => (
                  <Row key={invite.id}>
                    <Identity>
                      <Avatar>
                        {initials(invite.first_name, invite.last_name)}
                      </Avatar>
                      <Copy>
                        <strong>
                          {invite.first_name} {invite.last_name}
                        </strong>
                        <small>{invite.email}</small>
                      </Copy>
                    </Identity>
                    <div>
                      <StatusChip $tone="warning">Pending</StatusChip>
                      <Copy>
                        <small>{invite.role.name}</small>
                      </Copy>
                    </div>
                    <Scope>
                      <strong>
                        {invite.assigned_room_ids.length} assigned room
                        {invite.assigned_room_ids.length === 1 ? "" : "s"}
                      </strong>
                      <small>
                        Expires{" "}
                        {new Date(invite.expires_at).toLocaleDateString()}
                      </small>
                    </Scope>
                    <RowActions>
                      <IconButton
                        type="button"
                        onClick={() =>
                          void regenerate(
                            invite.id,
                            `${invite.first_name} ${invite.last_name}`,
                          )
                        }
                        disabled={busy === invite.id}
                        aria-label={`Regenerate activation link for ${invite.first_name} ${invite.last_name}`}
                      >
                        <ArrowPathIcon />
                      </IconButton>
                      <IconButton
                        type="button"
                        onClick={() =>
                          setConfirmation({
                            kind: "revoke",
                            id: invite.id,
                            name: `${invite.first_name} ${invite.last_name}`,
                          })
                        }
                        disabled={busy === invite.id}
                        aria-label={`Revoke invitation for ${invite.first_name} ${invite.last_name}`}
                      >
                        <XMarkIcon />
                      </IconButton>
                    </RowActions>
                  </Row>
                ))}
              </Directory>
            ) : (
              <Empty $accent="amber">
                <EnvelopeIcon />
                <h3>No pending invitations.</h3>
                <p>
                  New activation links appear here until accepted or revoked.
                </p>
              </Empty>
            )}
          </Section>
        </>
      )}
      {inviteOpen && workspace && (
        <InviteDialog
          workspace={workspace}
          roles={assignableRoles}
          onClose={() => setInviteOpen(false)}
          onCreated={(value, name) => {
            const url = absoluteHandoffUrl(value);
            setInviteOpen(false);
            setSecret({ kind: "activation", url, name });
            setCopied(false);
            refresh(
              "Invitation created. Copy the one-time activation link now.",
            );
          }}
        />
      )}
      {editMember && workspace && (
        <EditDialog
          member={editMember}
          workspace={workspace}
          roles={assignableRoles}
          onClose={() => setEditMember(null)}
          onSaved={() => {
            setEditMember(null);
            refresh("Staff role and room access saved.");
          }}
        />
      )}
      {secret && (
        <Modal titleId="one-time-secret-title" onClose={() => setSecret(null)}>
          <DialogHead>
            <div>
              <Eyebrow>
                <KeyIcon width={14} /> One-time secret
              </Eyebrow>
              <h2 id="one-time-secret-title">
                Copy this{" "}
                {secret.kind === "activation" ? "activation" : "password reset"}{" "}
                link now.
              </h2>
              <p>
                CareSync will not show this link again after this dialog closes.
                Share it privately with {secret.name}.
              </p>
            </div>
            <IconButton
              onClick={() => setSecret(null)}
              aria-label="Close one-time link"
            >
              <XMarkIcon />
            </IconButton>
          </DialogHead>
          <Secret>
            <code>{secret.url}</code>
            <ActionButton
              type="button"
              $variant="primary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(secret.url);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
            >
              <ClipboardDocumentIcon /> {copied ? "Copied" : "Copy link"}
            </ActionButton>
          </Secret>
          <Notice>
            <ShieldCheckIcon /> This is a local handoff link. Email delivery is
            not claimed or simulated.
          </Notice>
        </Modal>
      )}
      {confirmation && (
        <Modal
          titleId="staff-confirmation-title"
          onClose={() => setConfirmation(null)}
          busy={Boolean(busy)}
        >
          <DialogHead>
            <div>
              <Eyebrow>
                <ExclamationTriangleIcon width={14} /> Confirm access change
              </Eyebrow>
              <h2 id="staff-confirmation-title">
                {confirmation.kind === "revoke"
                  ? `Revoke ${confirmation.name}'s invitation?`
                  : `Suspend ${confirmation.member.first_name} ${confirmation.member.last_name}?`}
              </h2>
              <p>
                {confirmation.kind === "revoke"
                  ? "This activation link will stop working immediately. You can create a new invitation later."
                  : "This person will lose CareSync access immediately. Their identity and audit history will remain intact."}
              </p>
            </div>
            <IconButton
              onClick={() => setConfirmation(null)}
              disabled={Boolean(busy)}
              aria-label="Close confirmation"
            >
              <XMarkIcon />
            </IconButton>
          </DialogHead>
          <Notice $error>
            <ExclamationTriangleIcon /> This action changes access immediately
            after confirmation.
          </Notice>
          {error && (
            <Notice $error role="alert">
              <ExclamationTriangleIcon /> {error}
            </Notice>
          )}
          <FormActions>
            <ActionButton
              type="button"
              onClick={() => setConfirmation(null)}
              disabled={Boolean(busy)}
            >
              Keep access
            </ActionButton>
            <ActionButton
              type="button"
              $variant="danger"
              disabled={Boolean(busy)}
              onClick={() =>
                confirmation.kind === "revoke"
                  ? void revoke(confirmation.id)
                  : void changeStatus(confirmation.member, "suspended")
              }
            >
              {busy
                ? "Applying…"
                : confirmation.kind === "revoke"
                  ? "Revoke invitation"
                  : "Suspend access"}
            </ActionButton>
          </FormActions>
        </Modal>
      )}
    </Page>
  );
}

function InviteDialog({
  workspace,
  roles,
  onClose,
  onCreated,
}: {
  workspace: StaffWorkspace;
  roles: StaffRole[];
  onClose: () => void;
  onCreated: (url: string, name: string) => void;
}) {
  const [draft, setDraft] = useState(blankInvite);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const selectedRole = roles.find((role) => role.id === draft.role_id);
  const setRooms = (ids: string[]) =>
    setDraft((value) => ({
      ...value,
      assigned_room_ids: ids,
      assigned_facility_ids: roomFacilityIds(ids, workspace.rooms),
    }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const errors = validateStaffDraft(draft, selectedRole, workspace.rooms);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await staffApi.invite({
        ...draft,
        email: draft.email.trim().toLowerCase(),
        first_name: draft.first_name.trim(),
        last_name: draft.last_name.trim(),
      });
      onCreated(
        result.activation_url,
        `${draft.first_name.trim()} ${draft.last_name.trim()}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The invitation could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal titleId="invite-staff-title" onClose={onClose} busy={busy}>
      <DialogHead>
        <div>
          <Eyebrow>
            <UserPlusIcon width={14} /> New staff access
          </Eyebrow>
          <h2 id="invite-staff-title">Invite a team member.</h2>
          <p>
            Choose a fixed role and only the active rooms this person should
            reach.
          </p>
        </div>
        <IconButton
          onClick={onClose}
          disabled={busy}
          aria-label="Close invitation"
        >
          <XMarkIcon />
        </IconButton>
      </DialogHead>
      <Form onSubmit={submit}>
        <Grid>
          <Field>
            <span>First name</span>
            <input
              required
              autoComplete="given-name"
              value={draft.first_name}
              onChange={(event) =>
                setDraft((value) => ({
                  ...value,
                  first_name: event.target.value,
                }))
              }
            />
          </Field>
          <Field>
            <span>Last name</span>
            <input
              required
              autoComplete="family-name"
              value={draft.last_name}
              onChange={(event) =>
                setDraft((value) => ({
                  ...value,
                  last_name: event.target.value,
                }))
              }
            />
          </Field>
          <Field $wide>
            <span>Work email</span>
            <input
              required
              type="email"
              autoComplete="email"
              value={draft.email}
              onChange={(event) =>
                setDraft((value) => ({ ...value, email: event.target.value }))
              }
            />
          </Field>
          <Field $wide>
            <span>Role</span>
            <select
              required
              value={draft.role_id}
              onChange={(event) => {
                const role = roles.find(
                  (item) => item.id === event.target.value,
                );
                setDraft((value) => ({
                  ...value,
                  role_id: event.target.value,
                  assigned_room_ids:
                    role?.key === "educator" ? value.assigned_room_ids : [],
                  assigned_facility_ids:
                    role?.key === "educator" ? value.assigned_facility_ids : [],
                }));
              }}
            >
              <option value="">Choose a role</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
          </Field>
        </Grid>
        {selectedRole?.key === "educator" ? (
          <RoomChoices
            rooms={workspace.rooms}
            workspace={workspace}
            selected={draft.assigned_room_ids}
            onChange={setRooms}
          />
        ) : (
          selectedRole && (
            <Notice>
              <ShieldCheckIcon /> {selectedRole.name} receives organization-wide
              operational access defined by the server role.
            </Notice>
          )
        )}
        {error && (
          <Notice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </Notice>
        )}
        <FormActions>
          <ActionButton type="button" onClick={onClose} disabled={busy}>
            Cancel
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Creating…" : "Create invitation"}
          </ActionButton>
        </FormActions>
      </Form>
    </Modal>
  );
}

function EditDialog({
  member,
  workspace,
  roles,
  onClose,
  onSaved,
}: {
  member: StaffMember;
  workspace: StaffWorkspace;
  roles: StaffRole[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const availableRoles = roles.some((role) => role.id === member.role.id)
    ? roles
    : [member.role, ...roles];
  const [roleId, setRoleId] = useState(member.role.id);
  const [rooms, setRooms] = useState(member.assigned_room_ids);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const role = availableRoles.find((item) => item.id === roleId);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const facilities = roomFacilityIds(rooms, workspace.rooms);
    const draft = {
      email: member.email,
      first_name: member.first_name,
      last_name: member.last_name,
      role_id: roleId,
      assigned_facility_ids: facilities,
      assigned_room_ids: rooms,
    };
    const errors = validateStaffDraft(draft, role, workspace.rooms);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await staffApi.updateMember(member.membership_id, {
        role_id: roleId,
        assigned_facility_ids: facilities,
        assigned_room_ids: rooms,
      });
      onSaved();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Staff access could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal titleId="edit-staff-title" onClose={onClose} busy={busy}>
      <DialogHead>
        <div>
          <Eyebrow>
            <PencilSquareIcon width={14} /> Role and room access
          </Eyebrow>
          <h2 id="edit-staff-title">
            Edit {member.first_name} {member.last_name}.
          </h2>
          <p>
            Changes apply on the next authorized request. The server remains the
            final permission boundary.
          </p>
        </div>
        <IconButton
          onClick={onClose}
          disabled={busy}
          aria-label="Close access editor"
        >
          <XMarkIcon />
        </IconButton>
      </DialogHead>
      <Form onSubmit={submit}>
        <Field>
          <span>Role</span>
          <select
            value={roleId}
            onChange={(event) => {
              const next = availableRoles.find(
                (item) => item.id === event.target.value,
              );
              setRoleId(event.target.value);
              if (next?.key !== "educator") setRooms([]);
            }}
          >
            {availableRoles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        {role?.key === "educator" ? (
          <RoomChoices
            rooms={workspace.rooms}
            workspace={workspace}
            selected={rooms}
            onChange={setRooms}
          />
        ) : (
          <Notice>
            <ShieldCheckIcon /> This role receives organization-wide operational
            access.
          </Notice>
        )}
        {error && (
          <Notice $error role="alert">
            <ExclamationTriangleIcon /> {error}
          </Notice>
        )}
        <FormActions>
          <ActionButton type="button" onClick={onClose} disabled={busy}>
            Cancel
          </ActionButton>
          <ActionButton type="submit" $variant="primary" disabled={busy}>
            {busy ? "Saving…" : "Save access"}
          </ActionButton>
        </FormActions>
      </Form>
    </Modal>
  );
}
