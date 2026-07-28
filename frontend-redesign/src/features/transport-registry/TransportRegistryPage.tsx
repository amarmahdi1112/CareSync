import {
  ArrowPathIcon,
  CheckBadgeIcon,
  ChevronRightIcon,
  DocumentArrowUpIcon,
  DocumentMagnifyingGlassIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  ShieldCheckIcon,
  TruckIcon,
  UserCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import styled from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import { useSession } from '../../auth/SessionContext';
import { useRealtimeRefresh, useRealtimeState } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import {
  WorkforceDialog,
  WorkforceDialogActions,
  WorkforceDialogHeader,
} from '../staff-rota/components/WorkforceDialog';
import { TransportRegistryDialog, type TransportDialogAction } from './TransportRegistryDialog';
import { useTransportRegistryCapability } from './capability';
import {
  fetchPrivateEvidence,
  transportRegistryApi,
  type DriverReadiness,
  type TransportRegistryWorkspace,
  type TransportStaffRecord,
  type TransportVehicleRecord,
} from './transportRegistryApi';

const Page = styled.section`
  display: grid;
  gap: 16px;
  padding: clamp(16px, 2.2vw, 30px);
  color: ${({ theme }) => theme.color.text};
`;
const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  h1 { margin: 9px 0 7px; font-family: 'CareSync Display', ui-rounded, sans-serif; font-size: clamp(1.35rem, 2.3vw, 1.95rem); font-weight: 540; letter-spacing: -.042em; }
  p { max-width: 790px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .78rem; line-height: 1.62; }
  @media (max-width: 760px) { flex-direction: column; }
`;
const HeaderActions = styled.div`display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;`;
const Boundary = styled(GlassPanel)`
  display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:12px;padding:14px 16px;
  >svg{width:23px;color:${({ theme }) => theme.color.cyan};}
  h2{margin:0 0 3px;font-size:.82rem;font-weight:620;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.7rem;line-height:1.5;}
  @media(max-width:700px){grid-template-columns:auto 1fr;>span{grid-column:1/-1;justify-self:start;}}
`;
const Stats = styled.div`
  display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;
  @media(max-width:900px){grid-template-columns:repeat(2,minmax(0,1fr));}
  @media(max-width:480px){grid-template-columns:1fr;}
`;
const Stat = styled(GlassPanel)`
  display:grid;gap:5px;padding:14px 16px;span{color:${({ theme }) => theme.color.textMuted};font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;}strong{font-size:1.25rem;font-weight:550;}small{color:${({ theme }) => theme.color.textSoft};font-size:.65rem;}
`;
const Toolbar = styled(GlassPanel)`
  display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px;
  @media(max-width:680px){align-items:stretch;flex-direction:column;}
`;
const Tabs = styled.div`display:flex;gap:5px;`;
const Tab = styled.button<{ $active: boolean }>`
  min-height:39px;padding:0 14px;border:1px solid ${({ $active, theme }) => $active ? theme.color.cyan : 'transparent'};border-radius:9px 4px 9px 4px;color:${({ $active, theme }) => $active ? theme.color.text : theme.color.textMuted};background:${({ $active, theme }) => $active ? theme.color.control : 'transparent'};cursor:pointer;font-size:.73rem;font-weight:600;
`;
const Search = styled.label`
  display:flex;min-width:min(360px,100%);align-items:center;gap:8px;padding:0 11px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:10px 5px 10px 5px;background:${({ theme }) => theme.color.control};
  svg{width:17px;color:${({ theme }) => theme.color.textMuted};}input{width:100%;min-height:40px;border:0;outline:0;color:${({ theme }) => theme.color.text};background:transparent;font:inherit;font-size:.73rem;}
`;
const Workspace = styled.div`
  display:grid;grid-template-columns:minmax(245px,320px) minmax(0,1fr);gap:12px;align-items:start;
  @media(max-width:900px){grid-template-columns:1fr;}
`;
const Directory = styled(GlassPanel)`
  display:grid;gap:5px;max-height:calc(100vh - 230px);padding:9px;overflow:auto;scrollbar-gutter:stable;
  @media(max-width:900px){max-height:320px;}
`;
const DirectoryItem = styled.button<{ $active: boolean }>`
  display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:10px;width:100%;padding:11px;border:1px solid ${({ $active, theme }) => $active ? theme.color.cyan : 'transparent'};border-radius:10px 4px 10px 4px;color:${({ theme }) => theme.color.text};background:${({ $active, theme }) => $active ? theme.color.surfaceHover : 'transparent'};cursor:pointer;text-align:left;
  >svg:first-child{width:23px;color:${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textMuted};}.name{display:grid;gap:3px;min-width:0;strong{overflow:hidden;font-size:.75rem;font-weight:610;text-overflow:ellipsis;white-space:nowrap;}small{color:${({ theme }) => theme.color.textMuted};font-size:.63rem;}}.arrow{width:15px;color:${({ theme }) => theme.color.textMuted};}
  &:hover{background:${({ theme }) => theme.color.surfaceHover};}
`;
const Detail = styled.div`display:grid;gap:12px;min-width:0;`;
const DetailHeader = styled(GlassPanel)`
  display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:17px;
  h2{margin:5px 0;font-family:'CareSync Display',sans-serif;font-size:clamp(1.05rem,2vw,1.35rem);font-weight:560;letter-spacing:-.03em;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.68rem;line-height:1.5;}
  @media(max-width:650px){flex-direction:column;}
`;
const Actions = styled.div`display:flex;flex-wrap:wrap;justify-content:flex-end;gap:7px;@media(max-width:650px){justify-content:flex-start;}`;
const SummaryGrid = styled.div`display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;@media(max-width:700px){grid-template-columns:1fr;}`;
const Summary = styled(GlassPanel)`padding:13px 15px;span{display:block;margin-bottom:5px;color:${({ theme }) => theme.color.textMuted};font-size:.62rem;text-transform:uppercase;letter-spacing:.07em;}strong{font-size:.78rem;font-weight:610;}small{display:block;margin-top:5px;color:${({ theme }) => theme.color.textSoft};font-size:.64rem;line-height:1.45;}`;
const History = styled(GlassPanel)`
  display:grid;gap:10px;padding:15px;overflow:visible;
  header{display:flex;align-items:center;justify-content:space-between;gap:10px;}h3{margin:0;font-size:.8rem;font-weight:620;}p.empty{margin:0;padding:10px 0;color:${({ theme }) => theme.color.textMuted};font-size:.69rem;}
`;
const HistoryList = styled.div`display:grid;gap:7px;`;
const HistoryRow = styled.div`
  display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 11px;border:1px solid ${({ theme }) => theme.color.divider};border-radius:9px 4px 9px 4px;background:rgba(255,255,255,.018);
  .main{display:grid;gap:4px;min-width:0;strong{font-size:.72rem;font-weight:600;}small{color:${({ theme }) => theme.color.textMuted};font-size:.62rem;line-height:1.5;overflow-wrap:anywhere;}}.row-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px;}
  @media(max-width:570px){grid-template-columns:1fr;.row-actions{justify-content:flex-start;}}
`;
const SmallButton = styled.button`
  min-height:32px;padding:0 9px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:8px 4px 8px 4px;color:${({ theme }) => theme.color.textSoft};background:${({ theme }) => theme.color.control};cursor:pointer;font-size:.63rem;font-weight:600;&:hover{border-color:${({ theme }) => theme.color.cyan};color:${({ theme }) => theme.color.text};}&:disabled{opacity:.45;cursor:not-allowed;}
`;
const Warning = styled.div`display:flex;align-items:flex-start;gap:8px;padding:10px 12px;border:1px solid rgba(242,190,116,.32);border-radius:9px 4px 9px 4px;color:${({ theme }) => theme.color.amber};background:rgba(242,190,116,.06);font-size:.66rem;line-height:1.5;svg{width:16px;flex:0 0 auto;}`;
const StatePanel = styled(GlassPanel)`display:grid;min-height:300px;place-items:center;padding:28px;text-align:center;div{max-width:520px;}svg{width:34px;margin-bottom:10px;color:${({ theme }) => theme.color.cyan};}h2{margin:0 0 7px;font-size:1rem;}p{margin:0 0 14px;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;line-height:1.6;}`;
const EvidenceFrame = styled.iframe`width:100%;height:min(70vh,760px);border:1px solid ${({ theme }) => theme.color.border};border-radius:10px;background:#fff;`;
const EvidenceImage = styled.img`display:block;max-width:100%;max-height:70vh;margin:auto;border-radius:10px;object-fit:contain;`;
const Notice = styled.div`position:fixed;right:18px;bottom:18px;z-index:300;max-width:min(420px,calc(100vw - 36px));padding:12px 14px;border:1px solid rgba(142,216,176,.38);border-radius:11px 5px 11px 5px;color:${({ theme }) => theme.color.mint};background:${({ theme }) => theme.color.surfaceStrong};box-shadow:${({ theme }) => theme.shadow.panel};font-size:.7rem;`;

const label = (value: string): string => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const dateTime = (value: string | null): string => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Not recorded';
const dateOnly = (value: string | null): string => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`)) : 'No expiry';
const statusTone = (value: string): 'success' | 'warning' | 'info' | 'neutral' => ['verified', 'authorized', 'declared'].includes(value) ? 'success' : ['rejected', 'expired', 'revoked', 'blocked'].includes(value) ? 'warning' : 'info';

function TruncationWarning({ labels }: { labels: string[] }) {
  if (!labels.length) return null;
  return <Warning role="note"><ExclamationTriangleIcon /><span>Bounded history: {labels.join(', ')}. Earlier immutable records remain stored but are outside this workspace window.</span></Warning>;
}

function StaffDirectoryItem({ staff, active, onClick }: { staff: TransportStaffRecord; active: boolean; onClick: () => void }) {
  const latest = staff.readiness[0];
  return <DirectoryItem type="button" $active={active} onClick={onClick} aria-pressed={active}>
    <UserCircleIcon /><span className="name"><strong>{staff.first_name} {staff.last_name}</strong><small>{staff.capabilities[0] ? `${label(staff.capabilities[0].status)} · ${label(latest?.decision || 'not evaluated')}` : 'No driver declaration'}</small></span><ChevronRightIcon className="arrow" />
  </DirectoryItem>;
}

function VehicleDirectoryItem({ vehicle, active, onClick }: { vehicle: TransportVehicleRecord; active: boolean; onClick: () => void }) {
  const latest = vehicle.versions[0];
  return <DirectoryItem type="button" $active={active} onClick={onClick} aria-pressed={active}>
    <TruckIcon /><span className="name"><strong>{latest ? `${latest.make} ${latest.model}` : 'Vehicle record'}</strong><small>{latest?.plate_token || vehicle.id} · {vehicle.retired_at ? 'Retired' : label(vehicle.owner_kind)}</small></span><ChevronRightIcon className="arrow" />
  </DirectoryItem>;
}

function readinessSummary(readiness: DriverReadiness | undefined): string {
  if (!readiness) return 'Not evaluated';
  return readiness.reason_codes.length ? readiness.reason_codes.map(label).join(' · ') : label(readiness.decision);
}

function StaffDetail({ staff, workspace, ownMembershipId, evidenceUploadAvailable, onAction, onViewEvidence }: {
  staff: TransportStaffRecord;
  workspace: TransportRegistryWorkspace;
  ownMembershipId: string;
  evidenceUploadAvailable: boolean;
  onAction: (action: TransportDialogAction) => void;
  onViewEvidence: (path: string, title: string) => void;
}) {
  const capability = staff.capabilities[0];
  const authorization = staff.authorizations[0];
  const readiness = staff.readiness[0];
  const own = staff.membership_id === ownMembershipId;
  const truncation = [staff.capabilities_truncated && 'declaration history', ...staff.qualification_types_truncated.map((item) => `${label(item)} history`), staff.qualification_reviews_truncated && 'qualification reviews', staff.authorizations_truncated && 'authorizations', staff.readiness_truncated && 'readiness evaluations'].filter(Boolean) as string[];
  return <Detail>
    <DetailHeader $accent="cyan"><div><Eyebrow><UserCircleIcon width={14} /> Staff evidence file</Eyebrow><h2>{staff.first_name} {staff.last_name}</h2><p>Organization-scoped immutable evidence and decision history.</p></div><Actions>
      {own && <ActionButton type="button" onClick={() => onAction({ kind: 'self-declaration', staff })}>My declaration</ActionButton>}
      {own && <ActionButton type="button" onClick={() => onAction({ kind: 'self-qualification', staff })} disabled={!evidenceUploadAvailable}><DocumentArrowUpIcon /> Add my evidence</ActionButton>}
      <ActionButton type="button" onClick={() => onAction({ kind: 'authorization', staff })} disabled={!capability || !staff.qualifications.length}>Authorization</ActionButton>
      <ActionButton type="button" $variant="primary" onClick={() => onAction({ kind: 'readiness', staff, vehicles: workspace.vehicles })}>Re-evaluate</ActionButton>
    </Actions></DetailHeader>
    <SummaryGrid>
      <Summary $accent="plasma"><span>Declaration</span><strong>{capability ? label(capability.status) : 'Not declared'}</strong><small>{capability ? `${capability.licence_jurisdiction || '—'} · class ${capability.licence_class || '—'} · v${capability.version_number}` : 'Staff must make their own declaration.'}</small></Summary>
      <Summary $accent="cyan"><span>Authorization evidence</span><strong>{authorization ? label(authorization.decision) : 'No decision'}</strong><small>{authorization ? `${dateTime(authorization.reviewed_at)} · sequence ${authorization.decision_sequence}` : 'No employer evidence decision recorded.'}</small></Summary>
      <Summary $accent="amber"><span>Readiness review</span><strong>{readiness ? label(readiness.decision) : 'Not evaluated'}</strong><small>{readinessSummary(readiness)}</small></Summary>
    </SummaryGrid>
    <TruncationWarning labels={truncation} />
    <History><header><h3>Driver declaration history</h3><StatusChip $tone="neutral">{staff.capabilities.length} version{staff.capabilities.length === 1 ? '' : 's'}</StatusChip></header>{staff.capabilities.length ? <HistoryList>{staff.capabilities.map((item) => <HistoryRow key={item.id}><div className="main"><strong>v{item.version_number} · {label(item.status)}</strong><small>{item.willing_to_drive ? `Willing · ${label(item.vehicle_access)} · ${item.licence_jurisdiction || '—'} class ${item.licence_class || '—'}` : 'Declaration withdrawn'} · {dateTime(item.effective_at)}</small></div><StatusChip $tone={statusTone(item.status)}>{label(item.status)}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No declaration has been made. Managers cannot declare on another person’s behalf.</p>}</History>
    <History><header><h3>Qualifications & private evidence</h3><StatusChip $tone="neutral">{staff.qualifications.length} record{staff.qualifications.length === 1 ? '' : 's'}</StatusChip></header>{staff.qualifications.length ? <HistoryList>{staff.qualifications.map((item) => <HistoryRow key={item.id}><div className="main"><strong>{label(item.qualification_type)} · v{item.version_number}</strong><small>{label(item.status)} · expires {dateOnly(item.expiry_date)} · identifier {item.identifier_last4 ? `••••${item.identifier_last4}` : 'not recorded'}</small></div><div className="row-actions">{item.content_path && <SmallButton type="button" onClick={() => onViewEvidence(item.content_path!, `${staff.first_name} ${staff.last_name} · ${label(item.qualification_type)}`)}><DocumentMagnifyingGlassIcon width={14} /> View</SmallButton>} {item.evidence_present && item.status === 'declared' && <SmallButton type="button" onClick={() => onAction({ kind: 'qualification-review', staff, qualification: item })}>Review</SmallButton>}<StatusChip $tone={statusTone(item.status)}>{label(item.status)}</StatusChip></div></HistoryRow>)}</HistoryList> : <p className="empty">No qualification evidence has been supplied.</p>}</History>
    <History><header><h3>Qualification reviews</h3><StatusChip $tone="neutral">{staff.qualification_reviews.length}</StatusChip></header>{staff.qualification_reviews.length ? <HistoryList>{staff.qualification_reviews.map((item) => <HistoryRow key={item.id}><div className="main"><strong>{label(item.decision)}</strong><small>{label(item.reason_code)} · {dateTime(item.reviewed_at)}<br />source {item.source_qualification_version_id} → result {item.result_qualification_version_id}</small></div><StatusChip $tone={statusTone(item.decision)}>{label(item.decision)}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No independent qualification reviews recorded.</p>}</History>
    <History><header><h3>Authorization decisions</h3><StatusChip $tone="warning">Evidence only · no dispatch</StatusChip></header>{staff.authorizations.length ? <HistoryList>{staff.authorizations.map((item) => <HistoryRow key={item.id}><div className="main"><strong>Sequence {item.decision_sequence} · {label(item.decision)}</strong><small>{label(item.reason_code)} · {dateTime(item.reviewed_at)}{item.authorization_valid_from ? ` · ${dateTime(item.authorization_valid_from)} to ${dateTime(item.authorization_valid_until)}` : ''}</small></div><StatusChip $tone={statusTone(item.decision)}>{label(item.decision)}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No authorization evidence decision recorded.</p>}</History>
    <History><header><h3>Readiness evaluations</h3><StatusChip $tone="warning">Operational ready: false</StatusChip></header>{staff.readiness.length ? <HistoryList>{staff.readiness.map((item) => <HistoryRow key={item.id}><div className="main"><strong>Sequence {item.decision_sequence} · {label(item.decision)}</strong><small>{readinessSummary(item)} · {dateTime(item.evaluated_at)}{item.vehicle_id ? ` · vehicle ${item.vehicle_id}` : ''}</small></div><StatusChip $tone="warning">{label(item.decision)}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No readiness evaluation has been recorded.</p>}</History>
  </Detail>;
}

function VehicleDetail({ vehicle, evidenceUploadAvailable, onAction, onViewEvidence }: {
  vehicle: TransportVehicleRecord;
  evidenceUploadAvailable: boolean;
  onAction: (action: TransportDialogAction) => void;
  onViewEvidence: (path: string, title: string) => void;
}) {
  const latest = vehicle.versions[0];
  const truncation = [vehicle.versions_truncated && 'vehicle facts', ...vehicle.evidence_types_truncated.map((item) => `${label(item)} evidence`), vehicle.evidence_reviews_truncated && 'evidence reviews'].filter(Boolean) as string[];
  return <Detail>
    <DetailHeader $accent="plasma"><div><Eyebrow><TruckIcon width={14} /> {label(vehicle.owner_kind)}</Eyebrow><h2>{latest ? `${latest.make} ${latest.model}` : 'Vehicle record'}</h2><p>{latest?.plate_token || vehicle.id} · {vehicle.retired_at ? `Retired ${dateTime(vehicle.retired_at)}` : 'Active registry record'}</p></div><Actions>
      <ActionButton type="button" onClick={() => onAction({ kind: 'vehicle-version', vehicle })} disabled={Boolean(vehicle.retired_at)}>New version</ActionButton>
      <ActionButton type="button" onClick={() => onAction({ kind: 'vehicle-evidence', vehicle })} disabled={Boolean(vehicle.retired_at) || !evidenceUploadAvailable}><DocumentArrowUpIcon /> Add evidence</ActionButton>
      <ActionButton type="button" $variant="danger" onClick={() => onAction({ kind: 'vehicle-retire', vehicle })} disabled={Boolean(vehicle.retired_at)}>Retire</ActionButton>
    </Actions></DetailHeader>
    <SummaryGrid>
      <Summary $accent="plasma"><span>Latest facts</span><strong>{latest ? `${latest.model_year} ${latest.make} ${latest.model}` : 'No version'}</strong><small>{latest ? `${latest.plate_jurisdiction} ${latest.plate_token} · ${latest.color || 'color not recorded'}` : 'No vehicle facts returned.'}</small></Summary>
      <Summary $accent="cyan"><span>Capacity record</span><strong>{latest ? `${latest.child_passenger_capacity} child / ${latest.passenger_capacity} total` : '—'}</strong><small>{latest?.wheelchair_accessible ? 'Wheelchair accessible' : 'No wheelchair accessibility recorded'}</small></Summary>
      <Summary $accent="amber"><span>Evidence</span><strong>{vehicle.evidence.length} version{vehicle.evidence.length === 1 ? '' : 's'}</strong><small>{vehicle.evidence.filter((item) => item.status === 'verified').length} verified in the visible history.</small></Summary>
    </SummaryGrid>
    <TruncationWarning labels={truncation} />
    <History><header><h3>Vehicle facts history</h3><StatusChip $tone="neutral">Append only</StatusChip></header>{vehicle.versions.length ? <HistoryList>{vehicle.versions.map((item) => <HistoryRow key={item.id}><div className="main"><strong>v{item.version_number} · {item.model_year} {item.make} {item.model}</strong><small>{item.plate_jurisdiction} {item.plate_token} · {item.child_passenger_capacity}/{item.passenger_capacity} seats · {dateTime(item.effective_at)}</small></div><StatusChip $tone="info">Version {item.version_number}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No vehicle facts version returned.</p>}</History>
    <History><header><h3>Private evidence history</h3><StatusChip $tone={evidenceUploadAvailable ? 'success' : 'warning'}>{evidenceUploadAvailable ? 'Uploads available' : 'Uploads paused'}</StatusChip></header>{vehicle.evidence.length ? <HistoryList>{vehicle.evidence.map((item) => <HistoryRow key={item.id}><div className="main"><strong>{label(item.evidence_type)} · v{item.version_number}</strong><small>{item.original_filename || 'Private evidence'} · {Math.max(1, Math.round(item.byte_size / 1024))} KB · expires {dateOnly(item.expiry_date)}</small></div><div className="row-actions"><SmallButton type="button" onClick={() => onViewEvidence(item.content_path, `${latest ? `${latest.make} ${latest.model}` : 'Vehicle'} · ${label(item.evidence_type)}`)}>View</SmallButton>{item.status === 'provided' && <SmallButton type="button" onClick={() => onAction({ kind: 'vehicle-review', vehicle, evidence: item })}>Review</SmallButton>}<StatusChip $tone={statusTone(item.status)}>{label(item.status)}</StatusChip></div></HistoryRow>)}</HistoryList> : <p className="empty">No vehicle evidence supplied.</p>}</History>
    <History><header><h3>Evidence review decisions</h3><StatusChip $tone="neutral">{vehicle.evidence_reviews.length}</StatusChip></header>{vehicle.evidence_reviews.length ? <HistoryList>{vehicle.evidence_reviews.map((item) => <HistoryRow key={item.id}><div className="main"><strong>{label(item.decision)}</strong><small>{label(item.reason_code)} · {dateTime(item.reviewed_at)}<br />source {item.source_evidence_version_id} → result {item.result_evidence_version_id}</small></div><StatusChip $tone={statusTone(item.decision)}>{label(item.decision)}</StatusChip></HistoryRow>)}</HistoryList> : <p className="empty">No vehicle evidence reviews recorded.</p>}</History>
  </Detail>;
}

interface EvidencePreview { title: string; url: string | null; mediaType: 'application/pdf' | 'image/png' | 'image/jpeg' | null; error: string; loading: boolean; }

export default function TransportRegistryPage() {
  const session = useSession();
  const { capability } = useTransportRegistryCapability();
  const realtimeState = useRealtimeState();
  const organizationId = session.organization?.id || '';
  const [workspace, setWorkspace] = useState<TransportRegistryWorkspace | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [section, setSection] = useState<'staff' | 'vehicles'>('staff');
  const [query, setQuery] = useState('');
  const [selectedStaffId, setSelectedStaffId] = useState('');
  const [selectedVehicleId, setSelectedVehicleId] = useState('');
  const [dialog, setDialog] = useState<TransportDialogAction | null>(null);
  const [notice, setNotice] = useState('');
  const [preview, setPreview] = useState<EvidencePreview | null>(null);
  const evidenceRequest = useRef<AbortController | null>(null);
  const appliedWorkspaceGeneration = useRef(Number.NEGATIVE_INFINITY);

  const load = useCallback(async (signal?: AbortSignal) => {
    const result = await transportRegistryApi.workspace(signal);
    if (signal?.aborted) return;
    const generatedAt = Date.parse(result.generated_at);
    if (generatedAt < appliedWorkspaceGeneration.current) return;
    appliedWorkspaceGeneration.current = generatedAt;
    setWorkspace(result);
    setPhase('ready');
    setError('');
    setSelectedStaffId((current) => result.staff.some((item) => item.membership_id === current) ? current : result.staff[0]?.membership_id || '');
    setSelectedVehicleId((current) => result.vehicles.some((item) => item.id === current) ? current : result.vehicles[0]?.id || '');
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setPhase('loading');
    void load(controller.signal).catch((caught) => {
      if (controller.signal.aborted) return;
      setError(caught instanceof Error ? caught.message : 'The transport registry is unavailable.');
      setPhase('error');
    });
    return () => controller.abort();
  }, [load]);

  useRealtimeRefresh({
    scope: 'transport-registry', organizationId, enabled: phase !== 'error',
    eventPrefixes: ['transport_registry.'], entityTypes: featureIntegrationManifest['transport-registry'].realtimeEntities,
    refresh: async () => { await load(); },
  });

  useEffect(() => () => { evidenceRequest.current?.abort(); }, []);
  useEffect(() => { const objectUrl = preview?.url; return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); }; }, [preview?.url]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(''), 5000); return () => window.clearTimeout(timer); }, [notice]);

  const normalizedQuery = query.trim().toLowerCase();
  const staff = useMemo(() => (workspace?.staff || []).filter((item) => !normalizedQuery || `${item.first_name} ${item.last_name}`.toLowerCase().includes(normalizedQuery)), [normalizedQuery, workspace]);
  const vehicles = useMemo(() => (workspace?.vehicles || []).filter((item) => { const latest = item.versions[0]; return !normalizedQuery || `${latest?.make || ''} ${latest?.model || ''} ${latest?.plate_token || ''}`.toLowerCase().includes(normalizedQuery); }), [normalizedQuery, workspace]);
  const selectedStaff = staff.find((item) => item.membership_id === selectedStaffId) || staff[0];
  const selectedVehicle = vehicles.find((item) => item.id === selectedVehicleId) || vehicles[0];
  const pendingQualifications = workspace?.staff.reduce((total, item) => total + item.qualifications.filter((record) => record.status === 'declared' && record.evidence_present).length, 0) || 0;
  const pendingVehicleEvidence = workspace?.vehicles.reduce((total, item) => total + item.evidence.filter((record) => record.status === 'provided').length, 0) || 0;
  const scope = session.user && organizationId ? { actorUserId: session.user.id, organizationId } : null;

  const viewEvidence = async (path: string, title: string) => {
    evidenceRequest.current?.abort();
    const controller = new AbortController();
    evidenceRequest.current = controller;
    setPreview({ title, url: null, mediaType: null, error: '', loading: true });
    try {
      const content = await fetchPrivateEvidence(path, organizationId, controller.signal);
      if (controller.signal.aborted) return;
      setPreview({ title, url: URL.createObjectURL(content.blob), mediaType: content.mediaType, error: '', loading: false });
    } catch (caught) {
      if (controller.signal.aborted) return;
      setPreview({ title, url: null, mediaType: null, error: caught instanceof Error ? caught.message : 'Private evidence is unavailable.', loading: false });
    }
  };
  const closePreview = () => {
    evidenceRequest.current?.abort();
    evidenceRequest.current = null;
    setPreview(null);
  };

  if (phase === 'loading') return <Page><StatePanel $accent="cyan" role="status"><div><ArrowPathIcon /><h2>Loading registry evidence</h2><p>Confirming the canonical organization-scoped 0032 workspace.</p></div></StatePanel></Page>;
  if (phase === 'error' || !workspace || !scope) return <Page><StatePanel $accent="amber"><div><ExclamationTriangleIcon /><h2>Registry unavailable</h2><p>{error || 'The signed-in organization boundary is unavailable.'}</p><ActionButton type="button" onClick={() => { setPhase('loading'); void load().catch((caught) => { setError(caught instanceof Error ? caught.message : 'The registry is unavailable.'); setPhase('error'); }); }}><ArrowPathIcon /> Retry</ActionButton></div></StatePanel></Page>;

  return <Page>
    <Header><div><Eyebrow><ShieldCheckIcon width={15} /> Employer evidence boundary</Eyebrow><h1>Driver & vehicle registry</h1><p>Review declarations, private qualification evidence, authorization history, readiness blocks, and vehicle compliance without creating any child transportation authority.</p></div><HeaderActions><StatusChip $tone={realtimeState === 'connected' ? 'success' : 'warning'}>{realtimeState === 'connected' ? 'Live updates' : 'Recovery refresh'}</StatusChip><StatusChip $tone="info">0032</StatusChip></HeaderActions></Header>
    <Boundary $accent="cyan" role="status"><LockClosedIcon /><div><h2>Evidence registry only</h2><p>No children, addresses, routes, manifests, trips, dispatch, GPS, live location, or transportation assignments exist in this surface.</p></div><StatusChip $tone="warning">Operational driver ready: false</StatusChip></Boundary>
    <Stats>
      <Stat $accent="plasma"><span>Driver declarations</span><strong>{workspace.staff.filter((item) => item.capabilities[0]?.status === 'declared').length}</strong><small>{workspace.staff.length} active staff visible</small></Stat>
      <Stat $accent="amber"><span>Evidence awaiting review</span><strong>{pendingQualifications + pendingVehicleEvidence}</strong><small>{pendingQualifications} staff · {pendingVehicleEvidence} vehicle</small></Stat>
      <Stat $accent="cyan"><span>Vehicles</span><strong>{workspace.vehicles.filter((item) => !item.retired_at).length}</strong><small>{workspace.vehicles.filter((item) => item.retired_at).length} retired in view</small></Stat>
      <Stat $accent={capability?.evidence_upload_available ? 'cyan' : 'amber'}><span>Evidence pipeline</span><strong>{capability?.evidence_upload_available ? 'Available' : 'Uploads paused'}</strong><small>Metadata stays available; exact source retrieval is checked when opened</small></Stat>
    </Stats>
    {(workspace.staff_truncated || workspace.vehicles_truncated) && <TruncationWarning labels={[workspace.staff_truncated && 'staff directory after 200 records', workspace.vehicles_truncated && 'vehicle directory after 100 records'].filter(Boolean) as string[]} />}
    <Toolbar><Tabs role="tablist" aria-label="Registry sections"><Tab type="button" role="tab" aria-selected={section === 'staff'} $active={section === 'staff'} onClick={() => setSection('staff')}>Staff evidence</Tab><Tab type="button" role="tab" aria-selected={section === 'vehicles'} $active={section === 'vehicles'} onClick={() => setSection('vehicles')}>Vehicles</Tab></Tabs><Search><MagnifyingGlassIcon /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={section === 'staff' ? 'Search staff evidence…' : 'Search vehicle or plate…'} aria-label={section === 'staff' ? 'Search staff evidence' : 'Search vehicles'} /></Search>{section === 'vehicles' && <ActionButton type="button" $variant="primary" onClick={() => setDialog({ kind: 'vehicle-create' })}><PlusIcon /> Add vehicle</ActionButton>}</Toolbar>
    <Workspace>
      <Directory aria-label={section === 'staff' ? 'Staff evidence directory' : 'Vehicle directory'}>{section === 'staff' ? staff.map((item) => <StaffDirectoryItem key={item.membership_id} staff={item} active={item.membership_id === selectedStaff?.membership_id} onClick={() => setSelectedStaffId(item.membership_id)} />) : vehicles.map((item) => <VehicleDirectoryItem key={item.id} vehicle={item} active={item.id === selectedVehicle?.id} onClick={() => setSelectedVehicleId(item.id)} />)}{(section === 'staff' ? !staff.length : !vehicles.length) && <p style={{ padding: 12, color: '#b3bdc9', fontSize: '.7rem' }}>{query ? 'No matching records.' : `No ${section} records.`}</p>}</Directory>
      {section === 'staff' && selectedStaff ? <StaffDetail staff={selectedStaff} workspace={workspace} ownMembershipId={session.user?.membership_id || ''} evidenceUploadAvailable={Boolean(capability?.evidence_upload_available)} onAction={setDialog} onViewEvidence={viewEvidence} /> : section === 'vehicles' && selectedVehicle ? <VehicleDetail vehicle={selectedVehicle} evidenceUploadAvailable={Boolean(capability?.evidence_upload_available)} onAction={setDialog} onViewEvidence={viewEvidence} /> : <StatePanel><div><CheckBadgeIcon /><h2>No record selected</h2><p>Choose a visible record from the directory.</p></div></StatePanel>}
    </Workspace>
    {dialog && <TransportRegistryDialog action={dialog} scope={scope} evidenceUploadAvailable={Boolean(capability?.evidence_upload_available)} onClose={() => setDialog(null)} onCommitted={async (message) => {
      setNotice(message);
      try {
        await load();
      } catch {
        setNotice(`${message} The server confirmed this immutable change, but the canonical refresh is pending. Do not submit it again; live recovery will refresh this page.`);
      }
    }} />}
    {preview && <WorkforceDialog onClose={closePreview} busy={preview.loading} labelId="transport-evidence-title"><WorkforceDialogHeader><div><h2 id="transport-evidence-title">{preview.title}</h2><p>Private, no-store evidence fetched from the exact organization-scoped content route.</p></div><IconButton type="button" onClick={closePreview} aria-label="Close evidence"><XMarkIcon /></IconButton></WorkforceDialogHeader>{preview.loading ? <StatePanel role="status"><div><ArrowPathIcon /><p>Decrypting private evidence…</p></div></StatePanel> : preview.error ? <Warning role="alert"><ExclamationTriangleIcon />{preview.error}</Warning> : preview.url && preview.mediaType === 'application/pdf' ? <EvidenceFrame title={preview.title} src={preview.url} sandbox="allow-same-origin" /> : preview.url ? <EvidenceImage src={preview.url} alt={preview.title} /> : null}<WorkforceDialogActions><ActionButton type="button" onClick={closePreview}>Close private viewer</ActionButton></WorkforceDialogActions></WorkforceDialog>}
    {notice && <Notice role="status">{notice}</Notice>}
  </Page>;
}
