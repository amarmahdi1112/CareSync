import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import {
  BuildingOffice2Icon,
  CalendarDaysIcon,
  ClockIcon,
  CommandLineIcon,
  RectangleGroupIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useCommandData, type ResourceStatus } from '../../hooks/useCommandData';
import { useSession } from '../../auth/SessionContext';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import RecordReadinessPanel from './RecordReadinessPanel';
import RoomSafetyCompactSummary from '../rooms/RoomSafetyCompactSummary';

const sceneEnter = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
`;

const capacityResolve = keyframes`
  from { opacity: .35; transform: scaleX(0); }
  to { opacity: 1; transform: scaleX(1); }
`;

const Page = styled.div`
  display: grid;
  gap: 16px;
  animation: ${sceneEnter} 420ms ${({ theme }) => theme.motion.ease} both;
`;

const PageHeader = styled.header`
  display: flex;
  min-height: 86px;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 22px;

  h1 {
    margin: 8px 0 4px;
    font-family: 'CareSync Display', ui-rounded, sans-serif;
    font-size: clamp(1.85rem, 3vw, 2.5rem);
    font-weight: 500;
    letter-spacing: -.045em;
    line-height: 1.08;
  }

  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .875rem;
  }

  @media (max-width: 760px) {
    min-height: 0;
    align-items: flex-start;
    flex-direction: column;
  }
`;

const HeaderActions = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;

  @media (max-width: 620px) {
    width: 100%;
    align-items: stretch;
    flex-direction: column;
  }
`;

const DateCard = styled.div`
  display: flex;
  min-width: 238px;
  min-height: 48px;
  align-items: center;
  gap: 11px;
  padding: 9px 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textSoft};
  background:
    linear-gradient(120deg, color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 5%, transparent), transparent 42%),
    ${({ theme }) => theme.color.surfaceStrong};
  clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));

  svg { width: 19px; color: ${({ theme }) => theme.color.cyan}; }
  span { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; font-weight: 600; letter-spacing: .04em; }
  strong { display: block; margin-top: 2px; font-size: .8rem; font-weight: 500; }
`;

const PrimaryLink = styled(Link)<{ $secondary?: boolean }>`
  position: relative;
  display: inline-flex;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 15px;
  overflow: hidden;
  border: 1px solid ${({ $secondary, theme }) => $secondary ? theme.color.controlBorder : theme.color.cyan};
  color: ${({ $secondary, theme }) => $secondary ? theme.color.text : theme.color.ink};
  background: ${({ $secondary, theme }) => $secondary ? theme.color.surfaceStrong : theme.effect.primaryGradient};
  box-shadow: ${({ $secondary, theme }) => $secondary ? 'none' : theme.effect.primaryShadow};
  clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
  font-size: .8125rem;
  font-weight: 600;
  transition: transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease}, border-color ${({ theme }) => theme.motion.fast} ease, filter ${({ theme }) => theme.motion.fast} ease;

  &::after {
    position: absolute;
    inset: -30% auto -30% -38%;
    width: 28%;
    content: '';
    pointer-events: none;
    background: linear-gradient(90deg, transparent, color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 54%, transparent), transparent);
    transform: skewX(-16deg);
    transition: left 360ms ${({ theme }) => theme.motion.ease};
  }

  &:hover { transform: translateY(-1px); filter: brightness(1.035); }
  &:hover::after { left: 112%; }
  &:active { transform: scale(.985); }
  &:focus-visible {
    outline: 0;
    box-shadow: ${({ $secondary, theme }) => $secondary
      ? `inset 0 0 0 2px ${theme.color.cyan}`
      : `${theme.effect.primaryShadow}, inset 0 0 0 2px ${theme.color.ink}`};
  }
  svg { width: 17px; }
`;

const Gate = styled(GlassPanel)`
  display: grid;
  min-height: 360px;
  place-items: center;
  padding: 36px;
  text-align: center;
  svg { width: 46px; margin: 0 auto 14px; color: ${({ theme }) => theme.color.cyan}; }
  h2 { margin: 0 0 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.55rem; font-weight: 500; }
  p { max-width: 560px; margin: 0 auto 20px; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; line-height: 1.7; }
`;

const MetricRibbon = styled(GlassPanel)`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-radius: ${({ theme }) => theme.radius.md};

  @media (max-width: 960px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

const Metric = styled.div<{ $tone: 'plasma' | 'cyan' | 'mint' | 'amber' }>`
  position: relative;
  min-width: 0;
  min-height: 112px;
  padding: 18px 20px;
  overflow: hidden;
  border-left: 1px solid ${({ theme }) => theme.color.border};
  transition: background ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};

  &:first-child { border-left: 0; }
  &::before {
    position: absolute;
    top: 0;
    left: 20px;
    width: 72px;
    height: 2px;
    content: '';
    background: ${({ $tone, theme }) =>
      $tone === 'cyan' ? theme.color.cyan :
      $tone === 'mint' ? theme.color.mint :
      $tone === 'amber' ? theme.color.amber : theme.color.plasma};
  }
  &:hover { background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceHover} 34%, transparent); transform: translateY(-1px); }

  @media (max-width: 960px) {
    &:nth-child(odd) { border-left: 0; }
    &:nth-child(n + 3) { border-top: 1px solid ${({ theme }) => theme.color.border}; }
  }
  @media (max-width: 520px) {
    border-left: 0;
    &:nth-child(n + 2) { border-top: 1px solid ${({ theme }) => theme.color.border}; }
  }
`;

const MetricTop = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .75rem;
  font-weight: 600;
  letter-spacing: .045em;
  svg { width: 18px; color: ${({ theme }) => theme.color.cyan}; }
`;

const MetricValue = styled.div`
  display: flex;
  align-items: baseline;
  gap: 9px;
  margin-top: 12px;
  strong { font-family: 'CareSync Display', sans-serif; font-size: 1.9rem; font-weight: 500; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const OperationsDeck = styled(GlassPanel)`
  display: grid;
  min-height: 390px;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, .78fr);
  border-radius: ${({ theme }) => theme.radius.lg};

  @media (max-width: 980px) { grid-template-columns: 1fr; }
  @media (max-width: 520px) { order: 3; }
`;

const EnvironmentZone = styled.section`
  min-width: 0;
  padding: 24px;
`;

const ZoneHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.2rem; font-weight: 500; letter-spacing: -.025em; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; }
`;

const FacilityList = styled.div`display: grid;`;

const FacilityRow = styled.div`
  display: grid;
  grid-template-columns: 42px minmax(150px, .68fr) minmax(180px, 1fr) 96px;
  align-items: center;
  gap: 14px;
  min-height: 66px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  transition: background ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};
  &:hover { background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceHover} 34%, transparent); transform: translateX(2px); }

  @media (max-width: 680px) {
    grid-template-columns: 38px minmax(0, 1fr) auto;
    padding: 10px 0;
    > div:nth-child(3) { grid-column: 2 / -1; }
  }
`;

const FacilityIndex = styled.span`
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.color.cyan};
  clip-path: polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px));
  font-size: .75rem;
  font-weight: 600;
`;

const FacilityCopy = styled.div`
  min-width: 0;
  strong { display: block; overflow: hidden; font-size: .8125rem; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const Capacity = styled.div`
  display: grid;
  gap: 7px;
  min-width: 0;
  div { height: 6px; background: ${({ theme }) => theme.color.control}; overflow: hidden; }
  i { display: block; width: var(--capacity); height: 100%; background: linear-gradient(90deg, ${({ theme }) => theme.color.cyan}, ${({ theme }) => theme.color.mint}); transform-origin: left; animation: ${capacityResolve} 620ms ${({ theme }) => theme.motion.ease} both; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const FacilityStatus = styled.span`
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .75rem;
  font-weight: 600;
  text-align: right;
`;

const SystemsZone = styled.aside`
  position: relative;
  min-width: 0;
  padding: 24px;
  background:
    linear-gradient(145deg, color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 5%, transparent), transparent 40%),
    ${({ theme }) => theme.color.surfaceStrong};
  border-left: 1px solid ${({ theme }) => theme.color.border};
  &::after { position: absolute; top: 18px; right: 18px; width: 26px; height: 26px; content: ''; border-top: 1px solid ${({ theme }) => theme.color.plasma}; border-right: 1px solid ${({ theme }) => theme.color.plasma}; }
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.2rem; font-weight: 500; }
  > p { margin: 5px 0 16px; color: ${({ theme }) => theme.color.textMuted}; font-size: .8125rem; line-height: 1.5; }

  @media (max-width: 980px) { border-top: 1px solid ${({ theme }) => theme.color.border}; border-left: 0; }
`;

const SystemList = styled.div`display: grid; margin-bottom: 16px;`;

const SystemRow = styled.div`
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto;
  align-items: center;
  gap: 11px;
  min-height: 68px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  > svg { width: 18px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; font-size: .8125rem; font-weight: 600; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
  > span { color: ${({ theme }) => theme.color.textSoft}; font-size: .75rem; font-weight: 600; }
`;

const AttendanceStrip = styled(GlassPanel)`
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  align-items: stretch;
  border-radius: ${({ theme }) => theme.radius.md};

  @media (max-width: 820px) { grid-template-columns: 1fr; }
  @media (max-width: 520px) { order: 2; }
`;

const AttendanceCopy = styled.div`
  padding: 18px 20px;
  border-right: 1px solid ${({ theme }) => theme.color.border};
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; font-weight: 500; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.5; }
  @media (max-width: 820px) { border-right: 0; border-bottom: 1px solid ${({ theme }) => theme.color.border}; }
`;

const AttendanceGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  @media (max-width: 640px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
`;

const AttendanceCell = styled.div`
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 84px;
  flex-direction: column;
  justify-content: center;
  padding: 13px 16px;
  border-left: 1px solid ${({ theme }) => theme.color.border};
  &:first-child { border-left: 0; }
  strong { font-family: 'CareSync Display', sans-serif; font-size: 1.45rem; font-weight: 500; font-variant-numeric: tabular-nums; }
  span { margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
  @media (max-width: 640px) { &:nth-child(odd) { border-left: 0; } &:nth-child(n + 3) { border-top: 1px solid ${({ theme }) => theme.color.border}; } }
`;

const EmptyState = styled.div`
  padding: 26px 16px;
  border: 1px dashed ${({ theme }) => theme.color.borderStrong};
  color: ${({ theme }) => theme.color.textMuted};
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceHover} 24%, transparent);
  font-size: .8125rem;
  line-height: 1.6;
  text-align: center;
`;

function statusLabel(status: ResourceStatus): string {
  if (status === 'loading') return 'loading';
  if (status === 'live') return 'current';
  if (status === 'empty') return 'empty';
  if (status === 'error') return 'unavailable';
  return 'locked';
}

export default function DashboardPage() {
  const session = useSession();
  const canViewFamilyRecords = hasPermission(session.user, ACCESS.childcareRead);
  const { families, workspace, attendance, readiness, organizationReady, timeZone } = useCommandData({ includeFamilyStats: canViewFamilyRecords });
  const now = new Date();
  const userName = session.user?.first_name?.trim() || 'there';
  const organization = session.organization?.name || 'Your organization';
  const workspaceData = workspace.data;
  const attendanceData = attendance.data;
  const activeFacilities = workspaceData?.facilities.filter((item) => item.status === 'active') || [];
  const activeFacilityIds = new Set(activeFacilities.map((facility) => facility.id));
  const activeRooms = workspaceData?.rooms.filter((item) => item.is_active && activeFacilityIds.has(item.facility_id)) || [];
  const maxFacilityCapacity = Math.max(1, ...activeFacilities.map((facility) => facility.licensed_capacity || 0));
  let weekday = now.toLocaleDateString('en-CA', { weekday: 'long' });
  let operatingDate = now.toLocaleDateString('en-CA', { month: 'long', day: 'numeric', year: 'numeric' });
  let localHour = now.getHours();
  try {
    weekday = now.toLocaleDateString('en-CA', { weekday: 'long', timeZone });
    operatingDate = now.toLocaleDateString('en-CA', { month: 'long', day: 'numeric', year: 'numeric', timeZone });
    const hourPart = new Intl.DateTimeFormat('en-CA', { hour: '2-digit', hourCycle: 'h23', timeZone })
      .formatToParts(now)
      .find((part) => part.type === 'hour')?.value;
    if (hourPart) localHour = Number(hourPart);
  } catch {
    // The API validates timezones; browser-local formatting is a safe final fallback.
  }
  const greeting = localHour < 12 ? 'Good morning' : localHour < 17 ? 'Good afternoon' : 'Good evening';
  const value = (status: ResourceStatus, result: number | undefined) => status === 'live' || status === 'empty' ? result ?? 0 : '—';
  const operationalStatuses = canViewFamilyRecords ? [families.status, workspace.status, attendance.status] : [workspace.status, attendance.status];
  const isSyncing = operationalStatuses.some((status) => status === 'idle' || status === 'loading');
  const attendanceIsPartial = (attendanceData?.facilityFailures || 0) > 0;
  const hasAttention = (canViewFamilyRecords && families.status === 'error') || workspace.status === 'error' || attendance.status === 'error' || attendanceIsPartial;
  const currentFacilityCount = Math.max(0, (attendanceData?.facilityCount || 0) - (attendanceData?.facilityFailures || 0));
  const attendanceStatus = attendanceIsPartial
    ? `partial · ${currentFacilityCount}/${attendanceData?.facilityCount || 0}`
    : statusLabel(attendance.status);
  let attendanceContext = attendance.status === 'loading'
    ? 'Synchronizing facility rosters.'
    : attendance.status === 'error'
      ? 'Today’s attendance is unavailable.'
      : attendanceIsPartial
        ? `Partial totals · ${currentFacilityCount} of ${attendanceData?.facilityCount || 0} facilities current.`
        : `Actual roster states across ${attendanceData?.facilityCount || 0} active facilities.`;
  if (attendanceData?.refreshedAt) {
    try {
      const updated = new Intl.DateTimeFormat('en-CA', { hour: 'numeric', minute: '2-digit', timeZone }).format(new Date(attendanceData.refreshedAt));
      attendanceContext += ` Updated ${updated}.`;
    } catch {
      // Keep the completeness label even if a browser cannot format the saved timezone.
    }
  }

  return (
    <Page>
      <PageHeader>
        <div>
          <Eyebrow><CommandLineIcon width={14} /> {greeting}, {userName} · {organization}</Eyebrow>
          <h1>{weekday}, in focus.</h1>
          <p>{canViewFamilyRecords ? 'One calm view of families, care spaces, and today’s attendance.' : 'Your assigned rooms and today’s attendance, without unrelated child records.'}</p>
        </div>
        <HeaderActions>
          <DateCard>
            <CalendarDaysIcon aria-hidden="true" />
            <div><span>Operating date</span><strong>{operatingDate}</strong></div>
          </DateCard>
          <PrimaryLink to={canViewFamilyRecords ? '/families' : '/rooms'} $secondary>{canViewFamilyRecords ? <UserGroupIcon /> : <RectangleGroupIcon />} {canViewFamilyRecords ? 'Families' : 'My rooms'}</PrimaryLink>
          <PrimaryLink to="/attendance"><ClockIcon /> Open attendance</PrimaryLink>
        </HeaderActions>
      </PageHeader>

      {!organizationReady ? (
        <Gate $accent="cyan">
          <div>
            <ShieldCheckIcon />
            <h2>{session.status === 'anonymous' ? 'Sign in to open the dashboard.' : 'Verifying your organization.'}</h2>
            <p>Operational records stay locked until CareSync verifies that this account belongs to the active organization.</p>
            {session.status === 'anonymous' && <PrimaryLink to="/login">Open secure login</PrimaryLink>}
          </div>
        </Gate>
      ) : (
        <>
          <MetricRibbon as="section" role="list" aria-label="Organization metrics" aria-busy={isSyncing}>
            {canViewFamilyRecords ? <><Metric role="listitem" $tone="plasma"><MetricTop><span>FAMILY RECORDS</span><UserGroupIcon /></MetricTop><MetricValue><strong>{value(families.status, families.data?.families)}</strong><span>{statusLabel(families.status)}</span></MetricValue></Metric><Metric role="listitem" $tone="cyan"><MetricTop><span>ACTIVE CHILDREN</span><UsersIcon /></MetricTop><MetricValue><strong>{value(families.status, families.data?.active_children)}</strong><span>{statusLabel(families.status)}</span></MetricValue></Metric></> : <><Metric role="listitem" $tone="plasma"><MetricTop><span>ASSIGNED FACILITIES</span><BuildingOffice2Icon /></MetricTop><MetricValue><strong>{value(workspace.status, activeFacilities.length)}</strong><span>{statusLabel(workspace.status)}</span></MetricValue></Metric><Metric role="listitem" $tone="cyan"><MetricTop><span>NOT RECORDED</span><ClockIcon /></MetricTop><MetricValue><strong>{value(attendance.status, attendanceData?.pending)}</strong><span>{attendanceStatus}</span></MetricValue></Metric></>}
            <Metric role="listitem" $tone="mint"><MetricTop><span>ACTIVE ROOMS</span><RectangleGroupIcon /></MetricTop><MetricValue><strong>{value(workspace.status, activeRooms.length)}</strong><span>{statusLabel(workspace.status)}</span></MetricValue></Metric>
            <Metric role="listitem" $tone="amber"><MetricTop><span>ON SITE NOW</span><ClockIcon /></MetricTop><MetricValue><strong>{value(attendance.status, attendanceData?.onSite)}</strong><span>{attendanceStatus}</span></MetricValue></Metric>
          </MetricRibbon>
          {workspace.status === 'live' && workspaceData && activeFacilities[0] && (
            <RoomSafetyCompactSummary
              organizationId={session.organization!.id}
              facilityId={activeFacilities[0].id}
              facilityTimezone={activeFacilities[0].timezone}
              rooms={workspaceData.rooms}
            />
          )}

          <OperationsDeck>
            <EnvironmentZone>
              <ZoneHeader>
                <div><h2>Care environment</h2><p>Active facilities, rooms, and licensed capacity.</p></div>
                <StatusChip $tone="info">{activeFacilities.length} active</StatusChip>
              </ZoneHeader>
              {workspace.status === 'error' ? <EmptyState>{workspace.message}</EmptyState> : workspace.status === 'loading' ? <EmptyState>Loading facilities and rooms…</EmptyState> : activeFacilities.length ? (
                <FacilityList>
                  {activeFacilities.map((facility, index) => {
                    const roomCount = activeRooms.filter((room) => room.facility_id === facility.id).length;
                    const licensedCapacity = Math.max(0, facility.licensed_capacity || 0);
                    const capacityPercent = licensedCapacity > 0
                      ? Math.max(2, Math.round((licensedCapacity / maxFacilityCapacity) * 100))
                      : 0;
                    return (
                      <FacilityRow key={facility.id}>
                        <FacilityIndex>{String(index + 1).padStart(2, '0')}</FacilityIndex>
                        <FacilityCopy><strong>{facility.name}</strong><small>{facility.city || facility.province} · {roomCount} active {roomCount === 1 ? 'room' : 'rooms'}</small></FacilityCopy>
                        <Capacity style={{ '--capacity': `${capacityPercent}%` } as CSSProperties}><div aria-hidden="true"><i /></div><span>Relative licensed capacity</span></Capacity>
                        <FacilityStatus>{facility.licensed_capacity} licensed</FacilityStatus>
                      </FacilityRow>
                    );
                  })}
                </FacilityList>
              ) : <EmptyState>No active facilities are configured yet. Add a facility before creating rooms or recording attendance.</EmptyState>}
            </EnvironmentZone>

            <SystemsZone>
              <h2>Live data</h2>
              <p>Every signal comes from the authenticated organization boundary.</p>
              <SystemList>
                {canViewFamilyRecords ? <SystemRow><UserGroupIcon /><div><strong>Families and children</strong><small>{families.message || 'Active household records'}</small></div><span>{statusLabel(families.status)}</span></SystemRow> : <SystemRow><ShieldCheckIcon /><div><strong>Assigned care scope</strong><small>{activeRooms.length ? `${activeRooms.length} room assignments loaded` : 'No assigned rooms are currently available'}</small></div><span>{statusLabel(workspace.status)}</span></SystemRow>}
                <SystemRow><BuildingOffice2Icon /><div><strong>Facilities and rooms</strong><small>{workspace.message || `${activeFacilities.length} active facilities`}</small></div><span>{statusLabel(workspace.status)}</span></SystemRow>
                <SystemRow><ClockIcon /><div><strong>Today’s attendance</strong><small>{attendance.message || `${attendanceData?.enrolled ?? 0} enrolled children`}</small></div><span>{attendanceStatus}</span></SystemRow>
              </SystemList>
              <StatusChip role="status" aria-live="polite" $tone={hasAttention ? 'warning' : isSyncing ? 'info' : 'success'}>
                {hasAttention ? 'One or more records need attention' : isSyncing ? 'Synchronizing organization data' : 'Organization data connected'}
              </StatusChip>
            </SystemsZone>
          </OperationsDeck>

          <AttendanceStrip aria-live="polite" aria-busy={attendance.status === 'loading'}>
            <AttendanceCopy><h2>Today’s attendance</h2><p>{attendanceContext}</p></AttendanceCopy>
            {attendance.status === 'error' ? <EmptyState>{attendance.message}</EmptyState> : attendance.status === 'loading' ? <EmptyState>Loading today’s attendance…</EmptyState> : (
              <AttendanceGrid>
                <AttendanceCell><strong>{attendanceData?.enrolled ?? 0}</strong><span>Enrolled</span></AttendanceCell>
                <AttendanceCell><strong>{attendanceData?.pending ?? 0}</strong><span>Not recorded</span></AttendanceCell>
                <AttendanceCell><strong>{attendanceData?.onSite ?? 0}</strong><span>On site</span></AttendanceCell>
                <AttendanceCell><strong>{attendanceData?.completed ?? 0}</strong><span>Checked out</span></AttendanceCell>
                <AttendanceCell><strong>{attendanceData?.absent ?? 0}</strong><span>No-show</span></AttendanceCell>
              </AttendanceGrid>
            )}
          </AttendanceStrip>
          {canViewFamilyRecords && <RecordReadinessPanel status={readiness.status} data={readiness.data} message={readiness.message} />}
        </>
      )}
    </Page>
  );
}
