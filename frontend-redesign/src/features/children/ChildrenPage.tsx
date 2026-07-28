import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  AcademicCapIcon,
  ArrowPathIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  HomeModernIcon,
  LockClosedIcon,
  MapPinIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  PlusIcon,
  ShieldCheckIcon,
  SignalIcon,
  UserGroupIcon,
  UsersIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import {
  formatRosterDate,
  rosterSummary,
  type CareLane,
  type ChildListItem,
  type PlacementLabel,
} from './childrenModel';
import { useChildren, type ChildrenPhase } from './useChildren';
import {
  CHILD_DIRECTORY_PAGE_SIZE,
  type ChildDirectoryCareLaneFilter,
  type ChildDirectoryQuery,
  type ChildDirectoryStatusFilter,
} from './childrenApi';
import ChildEditor, { type ChildEditorRequest } from './ChildEditor';
import EnrollmentEditor from './EnrollmentEditor';
import ChildAvatar from './ChildAvatar';
import { childrenDirectoryWindow } from './childrenDirectoryView';

const enter = keyframes`
  from { opacity: 0; transform: translateY(14px); }
  to { opacity: 1; transform: translateY(0); }
`;

const shimmer = keyframes`
  from { transform: translateX(-110%); }
  to { transform: translateX(110%); }
`;

const Page = styled.div`
  display: grid;
  gap: 20px;
  animation: ${enter} 420ms ${({ theme }) => theme.motion.ease} both;
`;

const PageHeader = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 22px;

  h1 {
    margin: 10px 0 7px;
    font-family: 'CareSync Display', ui-rounded, sans-serif;
    font-size: clamp(1.85rem, 3vw, 2.5rem);
    font-weight: 500;
    letter-spacing: -.045em;
    line-height: 1.08;
  }

  p {
    max-width: 720px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: clamp(.78rem, 1.1vw, .92rem);
    line-height: 1.7;
  }

  @media (max-width: 760px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;

const SessionSignal = styled.div`
  display: grid;
  min-width: 220px;
  justify-items: end;
  gap: 7px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .75rem;
  text-align: right;

  @media (max-width: 760px) {
    min-width: 0;
    justify-items: start;
    text-align: left;
  }
`;

const MetricGrid = styled.section`
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 13px;

  @media (max-width: 1120px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

const Metric = styled(GlassPanel)`
  display: grid;
  min-height: 132px;
  align-content: space-between;
  padding: 17px;

  header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  header span { color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; }
  svg { width: 20px; color: ${({ theme }) => theme.color.plasmaBright}; }
  strong { display: block; margin-top: 22px; font-family: 'CareSync Display', sans-serif; font-size: 2.15rem; font-weight: 520; letter-spacing: -.07em; line-height: 1; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const StatePanel = styled(GlassPanel)`
  display: grid;
  min-height: 340px;
  place-items: center;
  padding: 40px 22px;
  text-align: center;
`;

const StateContent = styled.div`
  max-width: 520px;
  > svg { width: 44px; margin: 0 auto 18px; color: ${({ theme }) => theme.color.plasmaBright}; filter: drop-shadow(${({ theme }) => theme.shadow.glow}); }
  h2 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.35rem; font-weight: 580; letter-spacing: -.04em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .76rem; line-height: 1.7; }
  small { display: block; margin-top: 12px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const StateActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 9px;
  margin-top: 22px;
`;

const LoginLink = styled(Link)`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 0 15px;
  border: 1px solid ${({ theme }) => theme.color.plasmaBright};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.effect.primaryGradient};
  box-shadow: ${({ theme }) => theme.effect.primaryShadow};
  font-size: .8rem;
  font-weight: 600;
  svg { width: 18px; }
`;

const SkeletonList = styled.div`
  display: grid;
  width: min(760px, 100%);
  gap: 10px;
`;

const SkeletonRow = styled.div`
  position: relative;
  height: 66px;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  &::after { position: absolute; inset: 0; content: ''; background: linear-gradient(90deg, transparent, rgba(89,106,131,.12), transparent); animation: ${shimmer} 1.25s linear infinite; }
`;

const Toolbar = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(260px, 1fr) auto;
  align-items: end;
  gap: 14px;
  padding: 16px;

  @media (max-width: 890px) { grid-template-columns: 1fr; }
`;

const SearchControl = styled.div`
  label { display: block; margin: 0 0 7px 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
`;

const SearchField = styled.div`
  position: relative;
  display: flex;
  min-height: 46px;
  align-items: center;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  background: ${({ theme }) => theme.color.control};
  transition: border-color ${({ theme }) => theme.motion.fast} ease, background ${({ theme }) => theme.motion.fast} ease;

  &:focus-within { border-color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.control}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent); }
  > svg { width: 18px; margin-left: 13px; color: ${({ theme }) => theme.color.cyan}; }
  input { width: 100%; min-width: 0; padding: 0 42px 0 11px; border: 0; outline: 0; color: ${({ theme }) => theme.color.text}; background: transparent; font-size: .78rem; }
  input::placeholder { color: ${({ theme }) => theme.color.textMuted}; }
  button { position: absolute; right: 1px; display: grid; width: 44px; height: 44px; place-items: center; border: 0; border-radius: 9px; color: ${({ theme }) => theme.color.textMuted}; background: transparent; cursor: pointer; }
  button:hover { color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.surfaceHover}; }
  button svg { width: 16px; }
`;

const FilterGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
`;

const SelectControl = styled.div`
  label { display: block; margin: 0 0 7px 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  select {
    min-width: 150px;
    min-height: 46px;
    padding: 0 34px 0 12px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: ${({ theme }) => theme.radius.md};
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.surfaceStrong};
    cursor: pointer;
    font-size: .75rem;
  }
  select:focus { border-color: ${({ theme }) => theme.color.borderStrong}; }
  @media (max-width: 520px) { flex: 1; select { width: 100%; min-width: 0; } }
`;

const DirectoryPanel = styled(GlassPanel)`
  overflow: hidden;
`;

const DirectoryHeader = styled.header`
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 20px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.02rem; font-weight: 590; letter-spacing: -.035em; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
  @media (max-width: 600px) { align-items: flex-start; flex-direction: column; }
`;

const TableScroll = styled.div`
  overflow-x: auto;
  @media (max-width: 790px) { display: none; }
`;

const RosterTable = styled.table`
  width: 100%;
  border-collapse: collapse;
  text-align: left;

  caption { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  th { padding: 12px 16px; color: ${({ theme }) => theme.color.textMuted}; background: ${({ theme }) => theme.color.surfaceStrong}; font-size: .72rem; font-weight: 600; letter-spacing: .09em; text-transform: uppercase; white-space: nowrap; }
  td { padding: 14px 16px; border-top: 1px solid ${({ theme }) => theme.color.border}; color: ${({ theme }) => theme.color.textSoft}; font-size: .72rem; vertical-align: middle; }
  tbody tr { transition: background ${({ theme }) => theme.motion.fast} ease; }
  tbody tr:hover { background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceHover} 88%, ${({ theme }) => theme.color.plasma}); }
`;

const ChildIdentity = styled.div`
  display: grid;
  min-width: 210px;
  grid-template-columns: 39px 1fr;
  align-items: center;
  gap: 11px;
  strong { display: block; color: ${({ theme }) => theme.color.text}; font-size: .78rem; font-weight: 600; }
  small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; }
`;

const FamilyCell = styled.div`
  min-width: 150px;
  strong { display: block; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; font-weight: 600; }
  small { display: block; max-width: 175px; overflow: hidden; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
`;

const RecordLink = styled(Link)`
  color: ${({ theme }) => theme.color.text};
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 42%, transparent);
  text-underline-offset: 3px;
  &:hover { color: ${({ theme }) => theme.color.cyan}; }
`;

const ProfileLink = styled(Link)`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 14px;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.effect.primaryGradient};
  box-shadow: ${({ theme }) => theme.effect.primaryShadow};
  font-size: .78rem;
  font-weight: 600;
`;

const LanePill = styled.span<{ $lane: CareLane }>`
  display: inline-flex;
  min-height: 27px;
  align-items: center;
  padding: 4px 9px;
  border: 1px solid ${({ $lane, theme }) => $lane === 'OSC' ? theme.color.cyan : $lane === 'Daycare' ? theme.color.plasma : theme.color.amber};
  border-radius: ${({ theme }) => theme.radius.pill};
  color: ${({ $lane, theme }) => $lane === 'OSC' ? theme.color.cyan : $lane === 'Daycare' ? theme.color.plasmaBright : theme.color.amber};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .72rem;
  font-weight: 600;
`;

const PlacementPill = styled.span<{ $placement: PlacementLabel }>`
  display: inline-flex;
  min-height: 27px;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid ${({ $placement, theme }) => $placement === 'Current'
    ? theme.color.mint
    : $placement === 'Reserved'
      ? theme.color.cyan
      : theme.color.amber};
  border-radius: ${({ theme }) => theme.radius.pill};
  color: ${({ $placement, theme }) => $placement === 'Current'
    ? theme.color.mint
    : $placement === 'Reserved'
      ? theme.color.cyan
      : theme.color.amber};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .72rem;
  font-weight: 600;
`;

const MobileCards = styled.div`
  display: none;
  padding: 12px;
  @media (max-width: 790px) { display: grid; gap: 10px; }
`;

const ChildCard = styled.article`
  display: grid;
  gap: 14px;
  padding: 15px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.radius.md};
  background: ${({ theme }) => theme.color.surfaceStrong};
`;

const CardTop = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
`;

const CardFacts = styled.dl`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 11px;
  margin: 0;
  div { min-width: 0; }
  dt { color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
  dd { margin: 3px 0 0; overflow: hidden; color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; text-overflow: ellipsis; white-space: nowrap; }
`;

const EmptyDirectory = styled.div`
  display: grid;
  min-height: 270px;
  place-items: center;
  padding: 34px 20px;
  text-align: center;
  svg { width: 39px; margin: 0 auto 15px; color: ${({ theme }) => theme.color.textMuted}; }
  h3 { margin: 0 0 7px; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; }
  p { max-width: 450px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.65; }
  button { margin-top: 18px; }
`;

const DataNote = styled.footer`
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 13px 18px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .72rem;
  line-height: 1.55;
  svg { width: 16px; flex: 0 0 auto; color: ${({ theme }) => theme.color.cyan}; }
`;

const Pagination = styled.nav`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .72rem;
  > div { display: flex; align-items: center; gap: 8px; }
  button svg { width: 16px; }
  @media (max-width: 560px) { align-items: stretch; flex-direction: column; > div { display: grid; grid-template-columns: 1fr 1fr; } }
`;

const RowActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

const MutationNotice = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  border: 1px solid ${({ theme }) => theme.color.mint};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.textSoft};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, ${({ theme }) => theme.color.mint});
  font-size: .75rem;
  svg { width: 18px; color: ${({ theme }) => theme.color.mint}; }
`;

function phaseCopy(phase: ChildrenPhase, errorMessage?: string) {
  if (phase === 'checking-session') return {
    icon: LockClosedIcon,
    title: 'Verifying the secure session',
    description: 'The roster remains untouched until the redesign confirms your identity.',
  };
  if (phase === 'anonymous') return {
    icon: LockClosedIcon,
    title: 'Connect a secure session',
    description: 'Children data is never loaded in preview or anonymous mode. Sign in on this redesign port to view the organization roster.',
  };
  if (phase === 'session-unavailable') return {
    icon: ExclamationTriangleIcon,
    title: 'The secure session could not be verified',
    description: 'No children request was sent. Retry the identity check before reading organization records.',
  };
  if (phase === 'organization-required') return {
    icon: HomeModernIcon,
    title: 'Organization link required',
    description: 'This identity is not assigned to an organization. No children request was sent.',
  };
  if (phase === 'organization-loading') return {
    icon: HomeModernIcon,
    title: 'Confirming the organization boundary',
    description: 'The identity is authenticated, but roster reads remain blocked until organization metadata loads and matches it.',
  };
  if (phase === 'organization-unavailable') return {
    icon: ExclamationTriangleIcon,
    title: 'Organization metadata is unavailable',
    description: 'No children request was sent because the organization record could not be verified.',
  };
  if (phase === 'organization-mismatch') return {
    icon: ShieldCheckIcon,
    title: 'The children directory is safely locked',
    description: 'The authenticated identity and loaded organization metadata do not agree. No children request was sent.',
  };
  return {
    icon: ExclamationTriangleIcon,
    title: 'The roster could not be loaded',
    description: errorMessage || 'The backend did not return the organization roster.',
  };
}

function LoadState({
  phase,
  error,
  errorStatus,
  retry,
}: {
  phase: ChildrenPhase;
  error?: string;
  errorStatus?: number;
  retry: () => void;
}) {
  if (phase === 'loading') {
    return (
      <StatePanel $accent="cyan" aria-busy="true" aria-live="polite">
        <SkeletonList>
          <StateContent><ArrowPathIcon /><h2>Loading the organization directory</h2><p>Reading one bounded, organization-scoped child page.</p></StateContent>
          {[0, 1, 2, 3].map((value) => <SkeletonRow key={value} />)}
        </SkeletonList>
      </StatePanel>
    );
  }

  const copy = phaseCopy(phase, error);
  const Icon = copy.icon;
  const canRetryBoundary = phase === 'session-unavailable'
    || phase === 'organization-unavailable'
    || phase === 'organization-mismatch';
  const needsAttention = phase === 'error' || canRetryBoundary;
  return (
    <StatePanel $accent={needsAttention ? 'amber' : 'plasma'} role={needsAttention ? 'alert' : 'status'}>
      <StateContent>
        <Icon />
        <h2>{copy.title}</h2>
        <p>{copy.description}</p>
        <StateActions>
          {phase === 'anonymous' && <LoginLink to="/login"><LockClosedIcon /> Sign in to CareSync</LoginLink>}
          {phase === 'error' && <ActionButton $variant="primary" onClick={retry}><ArrowPathIcon /> Retry roster</ActionButton>}
          {canRetryBoundary && <ActionButton $variant="primary" onClick={retry}><ArrowPathIcon /> Retry secure verification</ActionButton>}
          {phase === 'error' && errorStatus === 401 && <LoginLink to="/login"><LockClosedIcon /> Reconnect session</LoginLink>}
        </StateActions>
      </StateContent>
    </StatePanel>
  );
}

function ChildRow({ child, onEdit, onEnrollment }: { child: ChildListItem; onEdit: () => void; onEnrollment: () => void }) {
  return (
    <tr>
      <td><ChildIdentity><ChildAvatar firstName={child.firstName} lastName={child.lastName} photoUrl={child.profilePhotoUrl} photoUpdatedAt={child.profilePhotoUpdatedAt} size={39} /><div><strong><RecordLink to={`/children/${encodeURIComponent(child.id)}`}>{child.fullName}</RecordLink></strong><small>Born {formatRosterDate(child.dateOfBirth)}</small></div></ChildIdentity></td>
      <td><FamilyCell><strong><RecordLink to={`/families/${encodeURIComponent(child.familyId)}`}>{child.familyName}</RecordLink></strong><small title={child.familyId}>Record · {child.familyId.slice(0, 8)}</small></FamilyCell></td>
      <td>{child.ageGroup}</td>
      <td><LanePill $lane={child.careLane}>{child.careLane}</LanePill></td>
      <td><PlacementPill $placement={child.placementLabel}>{child.placementLabel}</PlacementPill></td>
      <td>{formatRosterDate(child.enrollmentDate)}</td>
      <td><StatusChip $tone={child.status === 'active' ? 'success' : 'neutral'}>{child.status === 'active' ? 'Active' : 'Inactive'}</StatusChip></td>
      <td><RowActions><ProfileLink to={`/children/${encodeURIComponent(child.id)}`}>View profile</ProfileLink><ActionButton type="button" onClick={onEdit}><PencilSquareIcon /> Edit</ActionButton><ActionButton type="button" onClick={onEnrollment}><MapPinIcon /> Manage enrollment</ActionButton></RowActions></td>
    </tr>
  );
}

function ChildMobileCard({ child, onEdit, onEnrollment }: { child: ChildListItem; onEdit: () => void; onEnrollment: () => void }) {
  return (
    <ChildCard>
      <CardTop>
        <ChildIdentity><ChildAvatar firstName={child.firstName} lastName={child.lastName} photoUrl={child.profilePhotoUrl} photoUpdatedAt={child.profilePhotoUpdatedAt} size={39} /><div><strong><RecordLink to={`/children/${encodeURIComponent(child.id)}`}>{child.fullName}</RecordLink></strong><small><RecordLink to={`/families/${encodeURIComponent(child.familyId)}`}>{child.familyName}</RecordLink></small></div></ChildIdentity>
        <StatusChip $tone={child.status === 'active' ? 'success' : 'neutral'}>{child.status === 'active' ? 'Active' : 'Inactive'}</StatusChip>
      </CardTop>
      <CardFacts>
        <div><dt>Age group</dt><dd>{child.ageGroup}</dd></div>
        <div><dt>Care lane</dt><dd><LanePill $lane={child.careLane}>{child.careLane}</LanePill></dd></div>
        <div><dt>Placement</dt><dd><PlacementPill $placement={child.placementLabel}>{child.placementLabel}</PlacementPill></dd></div>
        <div><dt>Date of birth</dt><dd>{formatRosterDate(child.dateOfBirth)}</dd></div>
        <div><dt>Enrollment starts</dt><dd>{formatRosterDate(child.enrollmentDate)}</dd></div>
      </CardFacts>
      <RowActions><ProfileLink to={`/children/${encodeURIComponent(child.id)}`}>View profile</ProfileLink><ActionButton type="button" onClick={onEdit}><PencilSquareIcon /> Edit child</ActionButton><ActionButton type="button" onClick={onEnrollment}><MapPinIcon /> Manage enrollment</ActionButton></RowActions>
    </ChildCard>
  );
}

export default function ChildrenPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState('');
  const deferredSearch = useDeferredValue(searchInput.trim());
  const [careLane, setCareLane] = useState<ChildDirectoryCareLaneFilter>('all');
  const [status, setStatus] = useState<ChildDirectoryStatusFilter>('all');
  const [offset, setOffset] = useState(0);
  const directoryQuery = useMemo<ChildDirectoryQuery>(() => ({
    search: deferredSearch,
    status,
    careLane,
    familyId: null,
    limit: CHILD_DIRECTORY_PAGE_SIZE,
    offset,
  }), [careLane, deferredSearch, offset, status]);
  const { phase, children, page, error, retry, organizationName, organizationId } = useChildren(directoryQuery);
  const [editorRequest, setEditorRequest] = useState<ChildEditorRequest | null>(null);
  const [enrollmentChild, setEnrollmentChild] = useState<ChildListItem | null>(null);
  const [savedMessage, setSavedMessage] = useState('');
  const requestedFamilyId = searchParams.get('family') || '';
  const summary = page ? rosterSummary(page.counts) : null;
  const hasFilters = Boolean(deferredSearch || careLane !== 'all' || status !== 'all');
  const directoryWindow = childrenDirectoryWindow(page, hasFilters);
  const clearFilters = () => {
    setSearchInput('');
    setCareLane('all');
    setStatus('all');
    setOffset(0);
  };
  const linkNeedsAttention = phase === 'error'
    || phase === 'session-unavailable'
    || phase === 'organization-unavailable'
    || phase === 'organization-mismatch';
  const finishMutation = (message: string) => {
    setSavedMessage(message);
    setEditorRequest(null);
    retry();
  };
  const finishEnrollmentMutation = (message: string) => {
    setSavedMessage(message);
    setEnrollmentChild(null);
    retry();
  };

  useEffect(() => {
    if (phase !== 'ready' || !requestedFamilyId || editorRequest) return;
    setEditorRequest({ mode: 'create', familyId: requestedFamilyId });
    const next = new URLSearchParams(searchParams);
    next.delete('family');
    setSearchParams(next, { replace: true });
  }, [editorRequest, phase, requestedFamilyId, searchParams, setSearchParams]);

  useEffect(() => {
    if (phase !== 'ready' || !page || page.total === 0 || page.offset < page.total) return;
    setOffset(Math.floor((page.total - 1) / CHILD_DIRECTORY_PAGE_SIZE) * CHILD_DIRECTORY_PAGE_SIZE);
  }, [page, phase]);

  return (
    <Page>
      <PageHeader>
        <div>
          <Eyebrow><UserGroupIcon width={14} /> Care network · child records</Eyebrow>
          <h1>Children, clearly in view.</h1>
          <p>Create, review, update, and archive child records, then manage each child’s facility, program, and room enrollment inside the confirmed tenant boundary.</p>
        </div>
        <SessionSignal>
          <StatusChip $tone={phase === 'ready' ? 'success' : linkNeedsAttention ? 'warning' : 'info'}>
            {phase === 'ready' ? 'Live organization data' : linkNeedsAttention ? 'Link needs attention' : 'Secure gate'}
          </StatusChip>
          <span>{organizationName || 'Organization resolves after authentication'}</span>
          {phase === 'ready' && <ActionButton type="button" $variant="primary" onClick={() => setEditorRequest({ mode: 'create' })}><PlusIcon /> Add child</ActionButton>}
        </SessionSignal>
      </PageHeader>

      {phase !== 'ready' ? (
        <LoadState phase={phase} error={error?.message} errorStatus={error?.status} retry={retry} />
      ) : (
        <>
          {savedMessage && <MutationNotice role="status" aria-live="polite"><ShieldCheckIcon /> {savedMessage} The roster is refreshing.</MutationNotice>}
          {summary && <MetricGrid aria-label="Children directory summary">
            <Metric $interactive $accent="plasma"><header><UsersIcon /><span>Search scope</span></header><div><strong>{summary.total}</strong><p>Server-counted records before status and care filters</p></div></Metric>
            <Metric $interactive $accent="cyan"><header><SignalIcon /><span>Active status</span></header><div><strong>{summary.active}</strong><p>Active records in this search scope</p></div></Metric>
            <Metric $interactive $accent="plasma"><header><HomeModernIcon /><span>Daycare lane</span></header><div><strong>{summary.daycare}</strong><p>Current and reserved Daycare placements</p></div></Metric>
            <Metric $interactive $accent="cyan"><header><AcademicCapIcon /><span>OSC lane</span></header><div><strong>{summary.osc}</strong><p>Current and reserved OSC placements</p></div></Metric>
            <Metric $interactive $accent="plasma"><header><ClockIcon /><span>Reserved</span></header><div><strong>{summary.reserved}</strong><p>Future-effective placements, kept distinct from current</p></div></Metric>
          </MetricGrid>}

          <Toolbar $accent="cyan" aria-label="Roster filters">
            <SearchControl>
              <label htmlFor="children-search">Search roster</label>
              <SearchField>
                <MagnifyingGlassIcon aria-hidden="true" />
                <input
                  id="children-search"
                  type="search"
                  value={searchInput}
                  maxLength={200}
                  onChange={(event) => { setSearchInput(event.target.value); setOffset(0); }}
                  placeholder="Child name, family, or family file number"
                />
                {searchInput && <button type="button" onClick={() => { setSearchInput(''); setOffset(0); }} aria-label="Clear roster search"><XMarkIcon /></button>}
              </SearchField>
            </SearchControl>
            <FilterGroup>
              <SelectControl>
                <label htmlFor="children-care-lane">Care lane</label>
                <select id="children-care-lane" value={careLane} onChange={(event) => { setCareLane(event.target.value as ChildDirectoryCareLaneFilter); setOffset(0); }}>
                  <option value="all">All care types</option>
                  <option value="daycare">Daycare</option>
                  <option value="out_of_school_care">OSC</option>
                  <option value="unassigned">Unassigned</option>
                  <option value="needs_review">Needs review</option>
                </select>
              </SelectControl>
              <SelectControl>
                <label htmlFor="children-status">Saved status</label>
                <select id="children-status" value={status} onChange={(event) => { setStatus(event.target.value as ChildDirectoryStatusFilter); setOffset(0); }}>
                  <option value="all">All statuses</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                </select>
              </SelectControl>
            </FilterGroup>
          </Toolbar>

          <DirectoryPanel $accent="plasma">
            <DirectoryHeader>
              <div><h2>Organization directory</h2><p aria-live="polite">Showing {directoryWindow.start.toLocaleString()}–{directoryWindow.end.toLocaleString()} of {(page?.total || 0).toLocaleString()} filtered records</p></div>
              <ActionButton type="button" $variant="primary" onClick={() => setEditorRequest({ mode: 'create' })}><PlusIcon /> Add child</ActionButton>
            </DirectoryHeader>

            {directoryWindow.emptyState === 'first-record' ? (
              <EmptyDirectory><div><UserGroupIcon /><h3>No child records were returned</h3><p>The organization roster is connected and ready for its first child record.</p><ActionButton $variant="primary" onClick={() => setEditorRequest({ mode: 'create' })}><PlusIcon /> Add first child</ActionButton></div></EmptyDirectory>
            ) : directoryWindow.emptyState === 'filtered-empty' ? (
              <EmptyDirectory><div><MagnifyingGlassIcon /><h3>No records match these filters</h3><p>Try another child or family search, care lane, or saved status. No local filtering is hiding server records.</p><ActionButton onClick={clearFilters}><XMarkIcon /> Clear filters</ActionButton></div></EmptyDirectory>
            ) : (
              <>
                <TableScroll>
                  <RosterTable>
                    <caption>Organization children roster</caption>
                    <thead><tr><th>Child</th><th>Family</th><th>Age group</th><th><abbr title="Server-authored from the open enrollment program">Care lane</abbr></th><th>Placement</th><th>Starts</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>{children.map((child) => <ChildRow key={child.id} child={child} onEdit={() => setEditorRequest({ mode: 'edit', child })} onEnrollment={() => setEnrollmentChild(child)} />)}</tbody>
                  </RosterTable>
                </TableScroll>
                <MobileCards>{children.map((child) => <ChildMobileCard key={child.id} child={child} onEdit={() => setEditorRequest({ mode: 'edit', child })} onEnrollment={() => setEnrollmentChild(child)} />)}</MobileCards>
              </>
            )}

            {page && page.total > 0 && <Pagination aria-label="Children directory pages">
              <span>Page {directoryWindow.pageNumber} of {directoryWindow.pageCount}</span>
              <div>
                <ActionButton type="button" disabled={!directoryWindow.canGoBack} onClick={() => setOffset((value) => Math.max(0, value - CHILD_DIRECTORY_PAGE_SIZE))}><ChevronLeftIcon /> Previous</ActionButton>
                <ActionButton type="button" disabled={!directoryWindow.canGoForward} onClick={() => setOffset((value) => value + CHILD_DIRECTORY_PAGE_SIZE)}>Next <ChevronRightIcon /></ActionButton>
              </div>
            </Pagination>}
            <DataNote><ShieldCheckIcon /><span>This page is a 50-record, server-filtered directory. Medical data and enrollment history stay on the canonical child profile; facility-local current and future-reserved placements remain visibly distinct.</span></DataNote>
          </DirectoryPanel>
        </>
      )}
      {editorRequest && phase === 'ready' && organizationId && <ChildEditor request={editorRequest} organizationId={organizationId} onClose={() => setEditorRequest(null)} onSaved={finishMutation} onManageEnrollment={editorRequest.mode === 'edit' ? () => { setEnrollmentChild(editorRequest.child); setEditorRequest(null); } : undefined} />}
      {enrollmentChild && phase === 'ready' && organizationId && <EnrollmentEditor child={enrollmentChild} organizationId={organizationId} onClose={() => setEnrollmentChild(null)} onSaved={finishEnrollmentMutation} />}
    </Page>
  );
}
