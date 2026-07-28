import { useMemo, useState } from 'react';
import {
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  ShieldCheckIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import ChildAvatar from '../children/ChildAvatar';
import { attendanceLabel, attendanceTone, childNameParts, formatCareTime } from './careModel';
import {
  DAILY_CLOSE_ATTENTION_FLAGS,
  DAILY_CLOSE_CARE_TYPES,
  type DailyCloseAttentionFlag,
  type RoomDailyClosePreview,
} from './dailyCloseApi';

const Shell = styled.section`display:grid;gap:14px;min-width:0;`;
const Intro = styled(GlassPanel)`
  display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:17px 18px;
  h2{margin:7px 0 5px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.15rem,2.2vw,1.55rem);font-weight:560;letter-spacing:-.035em;}
  p{max-width:760px;margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.73rem;line-height:1.6;}
  small{flex:0 0 auto;color:${({ theme }) => theme.color.textMuted};font-size:.65rem;line-height:1.5;text-align:right;}
  @media(max-width:700px){flex-direction:column;small{text-align:left;}}
`;
const ReadOnlyNotice = styled(GlassPanel)`
  display:flex;align-items:flex-start;gap:10px;padding:13px 14px;border-color:${({ theme }) => theme.color.cyan};color:${({ theme }) => theme.color.textSoft};font-size:.72rem;line-height:1.55;
  svg{width:19px;flex:0 0 auto;color:${({ theme }) => theme.color.cyan};}
  strong{color:${({ theme }) => theme.color.text};font-weight:650;}
`;
const HeadlineMetrics = styled.div`display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;@media(max-width:780px){grid-template-columns:repeat(2,minmax(0,1fr));}@media(max-width:420px){grid-template-columns:1fr;}`;
const HeadlineMetric = styled(GlassPanel)`
  padding:13px 14px;span{display:flex;align-items:center;gap:7px;color:${({ theme }) => theme.color.textMuted};font-size:.64rem;text-transform:uppercase;letter-spacing:.065em;}svg{width:16px;color:${({ theme }) => theme.color.cyan};}strong{display:block;margin-top:7px;font-family:'CareSync Display',sans-serif;font-size:1.4rem;font-weight:560;}small{display:block;margin-top:3px;color:${({ theme }) => theme.color.textMuted};font-size:.63rem;}
`;
const TotalsGrid = styled.div`display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;@media(max-width:820px){grid-template-columns:1fr;}`;
const FactGroup = styled(GlassPanel)`
  padding:14px;h3{margin:0 0 10px;font-size:.76rem;font-weight:650;}dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:0;}div{min-width:0;padding:9px;border:1px solid ${({ theme }) => theme.color.border};border-radius:10px 4px 10px 4px;background:${({ theme }) => theme.color.surfaceStrong};}dt{overflow:hidden;color:${({ theme }) => theme.color.textMuted};font-size:.61rem;text-overflow:ellipsis;text-transform:capitalize;white-space:nowrap;}dd{margin:5px 0 0;font-size:.85rem;font-weight:620;}@media(max-width:440px){dl{grid-template-columns:repeat(2,minmax(0,1fr));}}
`;
const AttentionGroup = styled(FactGroup)`grid-column:1/-1;dl{grid-template-columns:repeat(5,minmax(0,1fr));}@media(max-width:820px){dl{grid-template-columns:repeat(3,minmax(0,1fr));}}@media(max-width:520px){dl{grid-template-columns:repeat(2,minmax(0,1fr));}}`;
const Toolbar = styled(GlassPanel)`display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px;@media(max-width:700px){align-items:stretch;flex-direction:column;}`;
const Search = styled.label`display:flex;align-items:center;gap:8px;min-width:min(340px,100%);min-height:44px;padding:0 11px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:11px 5px 11px 5px;background:${({ theme }) => theme.color.control};svg{width:17px;color:${({ theme }) => theme.color.textMuted};}input{width:100%;min-height:42px;border:0;outline:0;color:${({ theme }) => theme.color.text};background:transparent;font:inherit;font-size:.73rem;}`;
const Filters = styled.div`display:flex;flex-wrap:wrap;gap:7px;`;
const Filter = styled.button<{ $active?: boolean }>`min-height:44px;padding:0 11px;border:1px solid ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.controlBorder};border-radius:10px 4px 10px 4px;color:${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textSoft};background:${({ theme }) => theme.color.control};cursor:pointer;font:inherit;font-size:.66rem;font-weight:610;`;
const Roster = styled.div`display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;@media(max-width:980px){grid-template-columns:1fr;}`;
const ChildCard = styled(GlassPanel)<{ $attention?: boolean }>`display:grid;align-content:start;gap:12px;padding:15px;border-color:${({ $attention, theme }) => $attention ? theme.color.amber : theme.color.border};`;
const ChildHead = styled.header`display:flex;align-items:flex-start;justify-content:space-between;gap:12px;@media(max-width:460px){flex-direction:column;}`;
const Identity = styled.div`display:flex;align-items:center;gap:10px;min-width:0;h3{overflow:hidden;margin:0;font-size:.86rem;font-weight:620;text-overflow:ellipsis;white-space:nowrap;}p{margin:4px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.65rem;}`;
const AttendanceFacts = styled.dl`display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:0;div{padding:8px;border:1px solid ${({ theme }) => theme.color.border};border-radius:9px 4px 9px 4px;background:${({ theme }) => theme.color.surfaceStrong};}dt{color:${({ theme }) => theme.color.textMuted};font-size:.59rem;text-transform:uppercase;letter-spacing:.05em;}dd{margin:4px 0 0;font-size:.68rem;font-weight:610;}@media(max-width:420px){grid-template-columns:1fr;}`;
const ChildFactGrid = styled.div`display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:8px;@media(max-width:620px){grid-template-columns:1fr;}`;
const ChildFact = styled.section`padding:10px;border:1px solid ${({ theme }) => theme.color.border};border-radius:11px 5px 11px 5px;background:color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 88%, transparent);h4{margin:0 0 8px;font-size:.67rem;font-weight:650;}dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin:0;}div{display:flex;justify-content:space-between;gap:7px;color:${({ theme }) => theme.color.textMuted};font-size:.61rem;}dd{margin:0;color:${({ theme }) => theme.color.text};font-weight:620;}small{display:block;margin-top:8px;color:${({ theme }) => theme.color.textMuted};font-size:.59rem;line-height:1.4;}`;
const Attention = styled.div`display:flex;flex-wrap:wrap;gap:6px;min-height:24px;`;
const AttentionChip = styled.span`display:inline-flex;align-items:center;gap:5px;padding:5px 7px;border:1px solid ${({ theme }) => theme.color.amber};border-radius:8px 3px 8px 3px;color:${({ theme }) => theme.color.amber};background:color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 91%, ${({ theme }) => theme.color.amber});font-size:.6rem;svg{width:13px;}`;
const Clear = styled.p`display:flex;align-items:center;gap:6px;margin:0;color:${({ theme }) => theme.color.mint};font-size:.63rem;svg{width:15px;}`;
const Empty = styled(GlassPanel)`padding:34px 18px;text-align:center;color:${({ theme }) => theme.color.textMuted};svg{width:34px;}h3{margin:9px 0 5px;color:${({ theme }) => theme.color.text};font-size:.9rem;}p{margin:0;font-size:.7rem;}`;

type PreviewFilter = 'all' | 'attention' | 'on_site';

const CARE_LABELS: Record<(typeof DAILY_CLOSE_CARE_TYPES)[number], string> = {
  feeding: 'Feeding', diaper: 'Diaper', toilet: 'Toilet', sleep: 'Sleep', mood: 'Mood', activity: 'Activity',
};

const ATTENTION_LABELS: Record<DailyCloseAttentionFlag, string> = {
  open_sleep: 'Open sleep',
  medication_refused: 'Medication refused',
  medication_omitted: 'Medication omitted',
  incident_draft: 'Incident draft',
  incident_under_review: 'Incident under review',
};

function durationLabel(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!hours) return `${remainder}m`;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function optionalTime(value: string | null, timezone: string): string {
  return value ? formatCareTime(value, timezone) : '—';
}

function totalCounts(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function generatedLabel(value: string, timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  }).format(new Date(value));
}

export function DailyClosePreview({ preview }: { preview: RoomDailyClosePreview }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<PreviewFilter>('all');
  const attentionTotal = totalCounts(preview.totals.attention_flag_counts);
  const shown = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return preview.children.filter((child) => {
      if (filter === 'attention' && child.attention_flags.length === 0) return false;
      if (filter === 'on_site' && !child.currently_on_site) return false;
      return !normalized || child.child_name.toLowerCase().includes(normalized);
    });
  }, [filter, preview.children, query]);

  return <Shell aria-label="Daily close factual preview">
    <Intro $accent="cyan">
      <div><Eyebrow><ShieldCheckIcon width={14} /> Factual room roll-up</Eyebrow><h2>Daily close preview</h2><p>{preview.facility_name} · {preview.room_name} · {preview.service_date} · {preview.facility_timezone}</p></div>
      <small>Generated {generatedLabel(preview.generated_at, preview.facility_timezone)}<br />Private · no-store</small>
    </Intro>
    <ReadOnlyNotice $accent="cyan" role="note"><ShieldCheckIcon /><span><strong>Read-only facts preview.</strong> This view does not certify completeness or compliance, make a regulatory decision, or deliver anything to guardians.</span></ReadOnlyNotice>

    <HeadlineMetrics role="group" aria-label="Daily close room totals">
      <HeadlineMetric><span><UserGroupIcon /> Room children</span><strong>{preview.totals.child_count}</strong><small>{preview.totals.attendance_state_counts.not_recorded} not recorded · {preview.totals.attendance_state_counts.no_show} no-show</small></HeadlineMetric>
      <HeadlineMetric><span><CheckCircleIcon /> Currently on site</span><strong>{preview.totals.currently_on_site}</strong><small>{preview.totals.attendance_state_counts.checked_out} checked out</small></HeadlineMetric>
      <HeadlineMetric><span><ClockIcon /> Attendance time</span><strong>{durationLabel(preview.totals.accumulated_minutes)}</strong><small>Accumulated across this room</small></HeadlineMetric>
      <HeadlineMetric><span><ExclamationTriangleIcon /> Attention signals</span><strong>{attentionTotal}</strong><small>Factual flags; each child may have more than one</small></HeadlineMetric>
    </HeadlineMetrics>

    <TotalsGrid>
      <FactGroup><h3>Six care counts</h3><dl>{DAILY_CLOSE_CARE_TYPES.map((kind) => <div key={kind}><dt>{CARE_LABELS[kind]}</dt><dd>{preview.totals.care_counts[kind]}</dd></div>)}</dl></FactGroup>
      <FactGroup><h3>Medication outcomes</h3><dl>{(['administered', 'refused', 'omitted'] as const).map((outcome) => <div key={outcome}><dt>{outcome}</dt><dd>{preview.totals.medication_administration_counts[outcome]}</dd></div>)}</dl></FactGroup>
      <FactGroup><h3>Incident statuses</h3><dl>{(['draft', 'under_review', 'finalized'] as const).map((status) => <div key={status}><dt>{status.replaceAll('_', ' ')}</dt><dd>{preview.totals.incident_status_counts[status]}</dd></div>)}</dl></FactGroup>
      <FactGroup><h3>Attendance states</h3><dl>{(['not_recorded', 'on_site', 'checked_out', 'no_show'] as const).map((state) => <div key={state}><dt>{attendanceLabel(state)}</dt><dd>{preview.totals.attendance_state_counts[state]}</dd></div>)}</dl></FactGroup>
      <AttentionGroup><h3>Five attention flags</h3><dl>{DAILY_CLOSE_ATTENTION_FLAGS.map((flag) => <div key={flag}><dt>{ATTENTION_LABELS[flag]}</dt><dd>{preview.totals.attention_flag_counts[flag]}</dd></div>)}</dl></AttentionGroup>
    </TotalsGrid>

    <Toolbar>
      <Search><MagnifyingGlassIcon /><input aria-label="Search daily close children" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search children in this preview" /></Search>
      <Filters role="group" aria-label="Filter daily close children">
        <Filter type="button" $active={filter === 'all'} aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>All {preview.children.length}</Filter>
        <Filter type="button" $active={filter === 'attention'} aria-pressed={filter === 'attention'} onClick={() => setFilter('attention')}>Needs attention {preview.children.filter((child) => child.attention_flags.length > 0).length}</Filter>
        <Filter type="button" $active={filter === 'on_site'} aria-pressed={filter === 'on_site'} onClick={() => setFilter('on_site')}>On site {preview.totals.currently_on_site}</Filter>
      </Filters>
    </Toolbar>

    {shown.length ? <Roster role="list" aria-label="Daily close child facts">{shown.map((child) => {
      const name = childNameParts(child.child_name);
      return <ChildCard role="listitem" key={child.child_id} $accent={child.attention_flags.length ? 'amber' : 'cyan'} $attention={child.attention_flags.length > 0}>
        <ChildHead><Identity><ChildAvatar firstName={name.firstName} lastName={name.lastName} photoUrl={child.profile_photo_url} size={46} /><div><h3>{child.child_name}</h3><p>{durationLabel(child.accumulated_minutes)} accumulated attendance</p></div></Identity><StatusChip $tone={attendanceTone(child.attendance_state)}>{attendanceLabel(child.attendance_state)}</StatusChip></ChildHead>
        <AttendanceFacts><div><dt>First check-in</dt><dd>{optionalTime(child.first_check_in_at, preview.facility_timezone)}</dd></div><div><dt>Last checkout</dt><dd>{child.currently_on_site ? 'Still on site' : optionalTime(child.last_checkout_at, preview.facility_timezone)}</dd></div><div><dt>Total time</dt><dd>{durationLabel(child.accumulated_minutes)}</dd></div></AttendanceFacts>
        <ChildFactGrid>
          <ChildFact><h4>Care counts</h4><dl>{DAILY_CLOSE_CARE_TYPES.map((kind) => <div key={kind}><dt>{CARE_LABELS[kind]}</dt><dd>{child.care_counts[kind]}</dd></div>)}</dl><small>Most recent: {optionalTime(child.most_recent_care_at, preview.facility_timezone)}{child.open_sleep ? ' · sleep remains open' : ''}</small></ChildFact>
          <ChildFact><h4>Medication outcomes</h4><dl>{(['administered', 'refused', 'omitted'] as const).map((outcome) => <div key={outcome}><dt>{outcome}</dt><dd>{child.medication_administration_counts[outcome]}</dd></div>)}</dl><small>Most recent: {optionalTime(child.most_recent_medication_at, preview.facility_timezone)}</small></ChildFact>
          <ChildFact><h4>Incident statuses</h4><dl>{(['draft', 'under_review', 'finalized'] as const).map((status) => <div key={status}><dt>{status.replaceAll('_', ' ')}</dt><dd>{child.incident_status_counts[status]}</dd></div>)}</dl><small>Most recent: {optionalTime(child.most_recent_incident_at, preview.facility_timezone)}</small></ChildFact>
        </ChildFactGrid>
        <Attention role="group" aria-label={`Attention flags for ${child.child_name}`}>{child.attention_flags.length ? child.attention_flags.map((flag) => <AttentionChip key={flag}><ExclamationTriangleIcon /> {ATTENTION_LABELS[flag]}</AttentionChip>) : <Clear><CheckCircleIcon /> No attention flags in this preview</Clear>}</Attention>
      </ChildCard>;
    })}</Roster> : <Empty><MagnifyingGlassIcon /><h3>No children match this preview.</h3><p>Change the search or filter to return to the bounded room facts.</p></Empty>}
  </Shell>;
}

export default DailyClosePreview;
