import { useEffect, useRef } from 'react';
import { ArrowPathIcon, ExclamationTriangleIcon, UserGroupIcon, UserPlusIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import ChildAvatar from '../children/ChildAvatar';
import { formatProgramType } from '../../models/programTypes';
import type { RoomRecord, RoomRoster, RoomRosterChild, RoomWorkspace } from './roomsApi';

export type RosterLoadState = 'idle' | 'loading' | 'ready' | 'error';

interface RoomRosterPanelProps {
  room: RoomRecord;
  workspace: RoomWorkspace;
  roster: RoomRoster | null;
  rosterState: RosterLoadState;
  rosterError: string;
  organizationId: string;
  canManage: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

const Backdrop = styled.div`position:fixed;z-index:900;inset:0;display:grid;place-items:center;padding:24px;background:${({ theme }) => theme.color.overlay};backdrop-filter:blur(${({ theme }) => theme.effect.overlayBlur});@media(max-width:720px){padding:0;}`;
const Panel = styled(GlassPanel)`display:grid;width:min(920px,calc(100vw - 48px));max-height:calc(100dvh - 48px);grid-template-rows:auto minmax(0,1fr);overflow:hidden;border-radius:22px 8px 22px 8px;background:${({ theme }) => theme.effect.panelHighlight},${({ theme }) => theme.color.surface};@media(max-width:720px){width:100vw;max-height:100dvh;border-radius:0;}`;
const Header = styled.header`display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:23px 24px 18px;border-bottom:1px solid ${({ theme }) => theme.color.border};h2{margin:9px 0 5px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.55rem,3vw,2.25rem);font-weight:550;letter-spacing:-.05em;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.55;}`;
const Body = styled.div`display:grid;align-content:start;gap:16px;padding:20px 24px 32px;overflow-y:auto;@media(max-width:580px){padding-inline:14px;}`;
const Summary = styled.div`display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;@media(max-width:720px){grid-template-columns:repeat(2,minmax(0,1fr));}@media(max-width:440px){grid-template-columns:1fr;}`;
const SummaryItem = styled.div`padding:13px 14px;border:1px solid ${({ theme }) => theme.color.border};border-radius:13px;background:${({ theme }) => theme.color.surfaceStrong};span{display:block;color:${({ theme }) => theme.color.textMuted};font-size:.68rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;}strong{display:block;margin-top:6px;font-size:.82rem;font-weight:600;}`;
const RosterHeader = styled.div`display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:4px;h3{margin:0;font-family:'CareSync Display',sans-serif;font-size:1.05rem;}p{margin:3px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;line-height:1.5;}`;
const RosterList = styled.div`display:grid;gap:8px;`;
const ChildRow = styled.div`display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:12px;padding:13px;border:1px solid ${({ theme }) => theme.color.border};border-radius:13px;background:${({ theme }) => theme.color.surfaceStrong};strong{display:block;font-size:.76rem;font-weight:600;}p{margin:4px 0 0;color:${({ theme }) => theme.color.textMuted};font-size:.72rem;line-height:1.5;}`;
const ProfileName = styled(Link)`color:${({ theme }) => theme.color.text};text-decoration:underline;text-decoration-color:color-mix(in srgb,${({ theme }) => theme.color.cyan} 44%,transparent);text-underline-offset:3px;&:hover{color:${({ theme }) => theme.color.cyan};}`;
const Empty = styled.div`display:grid;min-height:150px;place-items:center;padding:24px;border:1px dashed ${({ theme }) => theme.color.border};border-radius:15px;text-align:center;svg{width:37px;margin-bottom:9px;color:${({ theme }) => theme.color.textMuted};}h3{margin:0 0 5px;font-size:.9rem;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.75rem;line-height:1.55;}`;
const NoEnrollments = styled.div`display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px;border:1px solid ${({ theme }) => theme.color.amber};border-radius:14px 6px 14px 6px;background:color-mix(in srgb,${({ theme }) => theme.color.surfaceStrong} 92%,${({ theme }) => theme.color.amber});p{margin:0;color:${({ theme }) => theme.color.textSoft};font-size:.75rem;line-height:1.55;}strong{color:${({ theme }) => theme.color.amber};}@media(max-width:560px){align-items:stretch;flex-direction:column;}`;
const ChildrenLink = styled(Link)`display:inline-flex;min-height:44px;flex:0 0 auto;align-items:center;justify-content:center;gap:8px;padding:0 14px;border:1px solid ${({ theme }) => theme.color.plasma};border-radius:11px 5px 11px 5px;background:color-mix(in srgb,${({ theme }) => theme.color.surfaceStrong} 90%,${({ theme }) => theme.color.plasma});font-size:.75rem;font-weight:600;svg{width:17px;}`;

function fullName(child: RoomRosterChild): string {
  return [child.first_name, child.middle_name, child.last_name].filter(Boolean).join(' ');
}

function chronologicalAge(dateOfBirth: string, facilityDate: string): string {
  const birth = dateOfBirth.slice(0, 10).split('-').map(Number);
  const current = facilityDate.split('-').map(Number);
  if (birth.length !== 3 || current.length !== 3 || [...birth, ...current].some((part) => !Number.isFinite(part))) return 'Age unavailable';
  let months = (current[0] - birth[0]) * 12 + current[1] - birth[1];
  if (current[2] < birth[2]) months -= 1;
  if (months < 0) return 'Age unavailable';
  const years = Math.floor(months / 12);
  const remainder = months % 12;
  return years ? `${years}y${remainder ? ` ${remainder}m` : ''}` : `${months} month${months === 1 ? '' : 's'}`;
}

function RosterChildren({ children, facilityDate, canManage, onClose }: { children: RoomRosterChild[]; facilityDate: string; canManage: boolean; onClose: () => void }) {
  return <RosterList>{children.map((child) => <ChildRow key={child.enrollment_id}>
    <ChildAvatar firstName={child.first_name} lastName={child.last_name} photoUrl={child.profile_photo_url} size={42} />
    <div><strong>{canManage ? <ProfileName to={`/children/${encodeURIComponent(child.child_id)}`} onClick={onClose}>{fullName(child)}</ProfileName> : fullName(child)}</strong><p>{child.family_name} family · {chronologicalAge(child.date_of_birth, facilityDate)} · {child.age_group ? `${child.age_group} saved band` : 'No saved age band'} · {child.enrollment_status} enrollment · starts {child.start_date.slice(0, 10)}</p></div>
  </ChildRow>)}</RosterList>;
}

export default function RoomRosterPanel({ room, workspace, roster, rosterState, rosterError, canManage, onClose, onRefresh }: RoomRosterPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab' || !panelRef.current) return;
      const focusable = [...panelRef.current.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', keyboard);
    requestAnimationFrame(() => panelRef.current?.querySelector<HTMLElement>('button,a[href]')?.focus());
    return () => { window.removeEventListener('keydown', keyboard); document.body.style.overflow = previousOverflow; previous?.focus(); };
  }, [onClose]);

  const entry = roster?.rooms.find((item) => item.room_id === room.id) || null;
  const roomProgram = workspace.programs.find((program) => program.id === room.program_id);
  const facilityTotal = roster
    ? roster.unassigned_children.length + roster.rooms.reduce((total, item) => total + item.children.length + item.reserved_children.length, 0)
    : 0;

  return <Backdrop onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <Panel ref={panelRef} $accent="cyan" role="dialog" aria-modal="true" aria-labelledby="room-roster-title" aria-describedby="room-roster-description">
      <Header><div><Eyebrow><UserGroupIcon width={14} /> Facility-date room roster</Eyebrow><h2 id="room-roster-title">{room.name}</h2><p id="room-roster-description">Current occupancy, reserved seats, and unassigned enrollments are separate projections. This view never silently treats a reservation as present.</p></div><IconButton type="button" onClick={onClose} aria-label="Close room roster"><XMarkIcon /></IconButton></Header>
      <Body>
        <Summary>
          <SummaryItem><span>Current occupancy</span><strong>{entry ? `${entry.occupancy} / ${entry.capacity}` : `— / ${room.capacity}`}</strong></SummaryItem>
          <SummaryItem><span>Reserved seats</span><strong>{entry?.reserved_children.length || 0}</strong></SummaryItem>
          <SummaryItem><span>Facility date</span><strong>{roster?.facility_date || '—'}</strong></SummaryItem>
          <SummaryItem><span>Program</span><strong>{roomProgram ? `${roomProgram.name} · ${formatProgramType(roomProgram.program_type)}` : 'Needs review'}</strong></SummaryItem>
        </Summary>

        {rosterState === 'loading' && <Empty aria-busy="true"><div><ArrowPathIcon /><h3>Loading verified roster</h3><p>CareSync is resolving current and reserved enrollment intervals in the facility timezone.</p></div></Empty>}
        {rosterState === 'error' && <Empty role="alert"><div><ExclamationTriangleIcon /><h3>The roster stayed read only</h3><p>{rosterError}</p><ActionButton type="button" onClick={onRefresh}><ArrowPathIcon /> Retry roster</ActionButton></div></Empty>}
        {rosterState === 'ready' && roster && <>
          {facilityTotal === 0 && <NoEnrollments><p><strong>No open enrollments exist at this facility.</strong><br />Create a pending enrollment from the child record, then approve its initial room placement.</p><ChildrenLink to="/children" onClick={onClose}><UserPlusIcon /> Open child records</ChildrenLink></NoEnrollments>}

          <RosterHeader><div><h3>Current in {room.name}</h3><p>Active assigned enrollments whose effective interval covers {roster.facility_date}.</p></div><StatusChip $tone={entry?.occupancy ? 'success' : 'neutral'}>{entry?.occupancy || 0} current</StatusChip></RosterHeader>
          {entry?.children.length ? <RosterChildren children={entry.children} facilityDate={roster.facility_date} canManage={canManage} onClose={onClose} /> : <Empty><div><UserGroupIcon /><h3>No current children in this room</h3><p>Reserved placements remain visible below and are not counted in current occupancy.</p></div></Empty>}

          <RosterHeader><div><h3>Reserved for {room.name}</h3><p>Future-effective or paused open enrollments reserving a seat.</p></div><StatusChip $tone={entry?.reserved_children.length ? 'warning' : 'neutral'}>{entry?.reserved_children.length || 0} reserved</StatusChip></RosterHeader>
          {entry?.reserved_children.length ? <RosterChildren children={entry.reserved_children} facilityDate={roster.facility_date} canManage={canManage} onClose={onClose} /> : <Empty><div><UserGroupIcon /><h3>No reserved seats</h3><p>No future-effective or paused enrollment currently reserves this room.</p></div></Empty>}

          {roster.unassigned_children.length > 0 && <NoEnrollments><p><strong>{roster.unassigned_children.length} open {roster.unassigned_children.length === 1 ? 'enrollment needs' : 'enrollments need'} initial placement.</strong><br />Use placement review to approve a DOB- and capacity-compatible room. Existing assigned placements cannot be overwritten here.</p><ChildrenLink to={`/rooms?facility_id=${encodeURIComponent(roster.facility_id)}`} onClick={onClose}><UserPlusIcon /> Open placement review</ChildrenLink></NoEnrollments>}
        </>}
      </Body>
    </Panel>
  </Backdrop>;
}
