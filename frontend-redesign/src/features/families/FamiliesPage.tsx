import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowPathIcon,
  CalendarDaysIcon,
  CheckBadgeIcon,
  ClockIcon,
  EnvelopeIcon,
  IdentificationIcon,
  LockClosedIcon,
  MagnifyingGlassIcon,
  PhoneIcon,
  PlusIcon,
  ShieldCheckIcon,
  Squares2X2Icon,
  TableCellsIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ACCESS, hasPermission } from '../../auth/accessModel';
import { useSession } from '../../auth/SessionContext';
import {
  ActionButton,
  Eyebrow,
  GlassPanel,
  StatusChip,
} from '../../components/ui/Primitives';
import { useFamilies } from './useFamilies';
import { resolveFamilyOrganizationBoundary } from './familyOrganizationBoundary';
import FamilyDrawer, { type FamilyDrawerRequest } from './FamilyDrawer';
import type {
  FamilyDirectoryRecord,
} from './types';

type ViewMode = 'cards' | 'table';

const enter = keyframes`
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
`;

const Page = styled.div`
  display: grid;
  gap: 20px;
  animation: ${enter} 250ms ${({ theme }) => theme.motion.ease} both;
`;

const PageHeader = styled.header`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;

  h1 {
    margin: 10px 0 6px;
    font-family: 'CareSync Display', ui-rounded, sans-serif;
    font-size: clamp(1.85rem, 3.4vw, 2.85rem);
    font-weight: 510;
    letter-spacing: -.045em;
    line-height: 1;
  }

  p {
    max-width: 760px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .875rem;
    line-height: 1.65;
  }

  @media (max-width: 760px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;

const HeaderStatus = styled.div`
  display: grid;
  justify-items: end;
  gap: 8px;
  text-align: right;

  small {
    max-width: 260px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .75rem;
    line-height: 1.5;
  }

  @media (max-width: 760px) {
    justify-items: start;
    text-align: left;
  }
`;

const ReadOnlyNotice = styled.div`
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 13px;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .8125rem;
  line-height: 1.55;

  svg {
    width: 18px;
    flex: 0 0 auto;
    color: ${({ theme }) => theme.color.cyan};
  }

  strong { color: ${({ theme }) => theme.color.text}; }
`;

const StatePanel = styled(GlassPanel)`
  display: grid;
  min-height: 360px;
  place-items: center;
  padding: clamp(30px, 7vw, 72px);
`;

const StateCopy = styled.div`
  display: grid;
  max-width: 580px;
  justify-items: center;
  gap: 12px;
  text-align: center;

  > svg {
    width: 48px;
    color: ${({ theme }) => theme.color.plasmaBright};
    filter: drop-shadow(${({ theme }) => theme.shadow.glow});
  }

  h2 {
    margin: 3px 0 0;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(1.45rem, 3vw, 2.25rem);
    font-weight: 540;
    letter-spacing: -.055em;
  }

  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .8125rem;
    line-height: 1.65;
  }
`;

const Spinner = styled(ArrowPathIcon)`
  color: ${({ theme }) => theme.color.cyan};
`;

const SessionLink = styled(Link)`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 16px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: ${({ theme }) => theme.radius.md};
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.color.cyan};
  box-shadow: ${({ theme }) => theme.shadow.cyan};
  font-size: .8125rem;
  font-weight: 600;
  transition:
    transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease},
    background ${({ theme }) => theme.motion.fast} ease;

  &:hover {
    background: ${({ theme }) => theme.color.plasmaBright};
    transform: translateY(-1px);
  }
`;

const Metrics = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 13px;

  @media (max-width: 1050px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 540px) { grid-template-columns: 1fr; }
`;

const Metric = styled(GlassPanel)`
  display: grid;
  min-height: 126px;
  align-content: space-between;
  gap: 18px;
  padding: 17px;
`;

const MetricHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;

  svg { width: 20px; color: ${({ theme }) => theme.color.plasmaBright}; }
  span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .72rem;
    font-weight: 600;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
`;

const MetricValue = styled.div`
  strong {
    display: block;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(1.55rem, 2.7vw, 2.3rem);
    font-weight: 520;
    letter-spacing: -.06em;
    line-height: 1;
  }

  small {
    display: block;
    margin-top: 5px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .75rem;
  }
`;

const Controls = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto auto;
  align-items: end;
  gap: 13px;
  padding: 16px;

  @media (max-width: 840px) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 560px) { grid-template-columns: 1fr; }
`;

const Field = styled.label`
  display: grid;
  gap: 7px;

  > span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .75rem;
    font-weight: 600;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
`;

const InputShell = styled.div`
  display: grid;
  min-height: 44px;
  grid-template-columns: 19px 1fr;
  align-items: center;
  gap: 9px;
  padding: 0 13px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  background: ${({ theme }) => theme.color.control};
  transition: border-color ${({ theme }) => theme.motion.fast} ease, box-shadow ${({ theme }) => theme.motion.fast} ease;

  &:focus-within {
    border-color: ${({ theme }) => theme.color.cyan};
    box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 18%, transparent);
  }

  svg { width: 18px; color: ${({ theme }) => theme.color.textMuted}; }
  input {
    width: 100%;
    min-width: 0;
    border: 0;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: transparent;
    font-size: .8125rem;
  }
  input::placeholder { color: ${({ theme }) => theme.color.textMuted}; }
`;

const Select = styled.select`
  min-width: 170px;
  min-height: 44px;
  padding: 0 34px 0 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  outline: 0;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .8125rem;

  &:focus { border-color: ${({ theme }) => theme.color.cyan}; }
`;

const ViewPicker = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  padding: 3px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: ${({ theme }) => theme.radius.md};
  background: ${({ theme }) => theme.color.surfaceStrong};
`;

const ViewButton = styled.button<{ $active: boolean }>`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 11px;
  border: 0;
  border-radius: 9px;
  color: ${({ $active, theme }) => $active ? theme.color.text : theme.color.textMuted};
  background: ${({ $active, theme }) => $active
    ? `color-mix(in srgb, ${theme.color.plasma} 18%, ${theme.color.surfaceStrong})`
    : 'transparent'};
  cursor: pointer;
  font-size: .75rem;
  font-weight: 600;
  transition:
    color ${({ theme }) => theme.motion.fast} ease,
    background ${({ theme }) => theme.motion.fast} ease,
    transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};

  &:hover {
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.surfaceHover};
    transform: translateY(-1px);
  }

  svg { width: 16px; }
`;

const ResultHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;

  strong { font-size: .78rem; font-weight: 600; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }

  @media (max-width: 640px) { align-items: flex-start; flex-direction: column; }
`;

const Pagination = styled.nav`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 8px 0;

  span {
    min-width: 150px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .75rem;
    text-align: center;
  }
`;

const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;

  @media (max-width: 1180px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 700px) { grid-template-columns: 1fr; }
`;

const FamilyCard = styled(GlassPanel)`
  display: grid;
  min-height: 300px;
  align-content: start;
  gap: 16px;
  padding: 18px;
`;

const FamilyCardHeader = styled.div`
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) auto;
  align-items: start;
  gap: 11px;
`;

const FamilyAvatar = styled.div`
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.plasma};
  border-radius: 13px;
  color: ${({ theme }) => theme.color.plasmaBright};
  background: ${({ theme }) => theme.color.surfaceStrong};
  svg { width: 22px; }
`;

const FamilyTitle = styled.div`
  min-width: 0;
  h2 {
    margin: 1px 0 4px;
    overflow: hidden;
    font-family: 'CareSync Display', sans-serif;
    font-size: .98rem;
    font-weight: 580;
    letter-spacing: -.035em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const ContactBlock = styled.div`
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  background: ${({ theme }) => theme.color.surfaceStrong};

  strong { font-size: .8125rem; font-weight: 600; }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const ContactLine = styled.div`
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .8125rem;

  svg { width: 15px; flex: 0 0 auto; color: ${({ theme }) => theme.color.textMuted}; }
  a, span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  a:hover { color: ${({ theme }) => theme.color.cyan}; }
`;

const ChildrenSection = styled.div`
  display: grid;
  gap: 9px;
  padding-top: 14px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
`;

const ChildrenHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .72rem;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
`;

const ChildPills = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
`;

const ChildPill = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.radius.pill};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .75rem;

  em { color: ${({ theme }) => theme.color.cyan}; font-size: .72rem; font-style: normal; }
`;

const ChildPillLink = styled(Link)`
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.radius.pill};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .75rem;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; color: ${({ theme }) => theme.color.cyan}; }
  em { color: ${({ theme }) => theme.color.cyan}; font-size: .72rem; font-style: normal; }
`;

const ProfileLink = styled(Link)`
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid ${({ theme }) => theme.color.cyan};
  border-radius: 11px 5px 11px 5px;
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.effect.primaryGradient};
  box-shadow: ${({ theme }) => theme.effect.primaryShadow};
  font-size: .8rem;
  font-weight: 600;
`;

const NameLink = styled(Link)`
  color: ${({ theme }) => theme.color.text};
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, ${({ theme }) => theme.color.cyan} 42%, transparent);
  text-underline-offset: 3px;
  &:hover { color: ${({ theme }) => theme.color.cyan}; }
`;

const CardFooter = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .72rem;

  span { display: inline-flex; align-items: center; gap: 6px; }
  svg { width: 14px; }
`;

const TablePanel = styled(GlassPanel)`
  overflow: hidden;
`;

const TableScroller = styled.div`
  overflow-x: auto;
`;

const Table = styled.table`
  width: 100%;
  min-width: 900px;
  border-collapse: collapse;

  th {
    padding: 13px 16px;
    border-bottom: 1px solid ${({ theme }) => theme.color.border};
    color: ${({ theme }) => theme.color.textMuted};
    background: ${({ theme }) => theme.color.surfaceStrong};
    font-size: .72rem;
    font-weight: 600;
    letter-spacing: .08em;
    text-align: left;
    text-transform: uppercase;
  }

  td {
    padding: 15px 16px;
    border-bottom: 1px solid ${({ theme }) => theme.color.border};
    color: ${({ theme }) => theme.color.textSoft};
    font-size: .8125rem;
    vertical-align: middle;
  }

  tbody tr:last-child td { border-bottom: 0; }
  tbody tr { transition: background ${({ theme }) => theme.motion.fast} ease; }
  tbody tr:hover { background: ${({ theme }) => theme.color.surfaceHover}; }
`;

const FamilyCell = styled.div`
  display: flex;
  min-width: 210px;
  align-items: center;
  gap: 10px;
  strong { display: block; color: ${({ theme }) => theme.color.text}; font-size: .8125rem; }
  small { display: block; margin-top: 2px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

const ContactCell = styled.div`
  min-width: 180px;
  strong { display: block; color: ${({ theme }) => theme.color.textSoft}; font-size: .8125rem; }
  small { display: block; max-width: 230px; margin-top: 2px; overflow: hidden; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; text-overflow: ellipsis; white-space: nowrap; }
`;

const ChildrenCell = styled.div`
  display: flex;
  min-width: 170px;
  flex-wrap: wrap;
  gap: 5px;
`;

const EmptyResults = styled(GlassPanel)`
  display: grid;
  min-height: 260px;
  place-items: center;
  padding: 32px;
`;

const SkeletonGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  @media (max-width: 1000px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 650px) { grid-template-columns: 1fr; }
`;

const SkeletonCard = styled(GlassPanel)`
  min-height: 270px;
  padding: 18px;
`;

const SkeletonLine = styled.div<{ $width?: string; $height?: string }>`
  width: ${({ $width }) => $width || '100%'};
  height: ${({ $height }) => $height || '12px'};
  margin-bottom: 13px;
  border-radius: 999px;
  border: 1px solid ${({ theme }) => theme.color.divider};
  background: ${({ theme }) => theme.color.surfaceStrong};
`;

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusTone(status: string): 'success' | 'warning' | 'info' | 'neutral' {
  const normalized = status.toLowerCase();
  if (normalized === 'active') return 'success';
  if (normalized === 'pending') return 'warning';
  if (normalized === 'inactive' || normalized === 'archived') return 'neutral';
  return 'info';
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return date.toLocaleDateString('en-CA', { year: 'numeric', month: 'short', day: 'numeric' });
}

function FamilyCardView({ family }: { family: FamilyDirectoryRecord }) {
  const contact = family.primary_contact;
  const children = family.active_children;
  const additionalChildren = Math.max(0, family.active_child_count - children.length);

  return (
    <FamilyCard $accent="plasma">
      <FamilyCardHeader>
        <FamilyAvatar><UserGroupIcon aria-hidden="true" /></FamilyAvatar>
        <FamilyTitle>
          <h2 title={family.name}><NameLink to={`/families/${encodeURIComponent(family.id)}`}>{family.name}</NameLink></h2>
          <p>{family.file_number ? `File ${family.file_number}` : 'No file number recorded'}</p>
        </FamilyTitle>
        <StatusChip $tone={statusTone(family.status)}>{titleCase(family.status)}</StatusChip>
      </FamilyCardHeader>

      <ContactBlock>
        <div><strong>{contact ? `${contact.first_name} ${contact.last_name}` : 'No primary contact listed'}</strong><small>Current primary-contact directory summary</small></div>
        <ContactLine>
          <PhoneIcon aria-hidden="true" />
          {contact?.cell_phone ? <a href={`tel:${contact.cell_phone}`}>{contact.cell_phone}</a> : <span>No phone recorded</span>}
        </ContactLine>
        <ContactLine>
          <EnvelopeIcon aria-hidden="true" />
          {contact?.email ? <a href={`mailto:${contact.email}`}>{contact.email}</a> : <span>No email recorded</span>}
        </ContactLine>
      </ContactBlock>

      <ChildrenSection>
        <ChildrenHeader><span>Active children</span><span>{family.active_child_count}</span></ChildrenHeader>
        <ChildPills>
          {children.length === 0 && <ChildPill>{family.active_child_count ? `${family.active_child_count} active · preview unavailable` : 'No active children'}</ChildPill>}
          {children.map((child) => (
            <ChildPillLink key={child.id} to={`/children/${encodeURIComponent(child.id)}`}>
              {child.first_name} {child.last_name}
              <em>{child.age_group || 'Unspecified'}</em>
            </ChildPillLink>
          ))}
          {additionalChildren > 0 && <ChildPill>+{additionalChildren} more</ChildPill>}
        </ChildPills>
      </ChildrenSection>

      <CardFooter>
        <span><CalendarDaysIcon aria-hidden="true" /> Added {formatDate(family.created_at)}</span>
        <ProfileLink to={`/families/${encodeURIComponent(family.id)}`}>Open profile</ProfileLink>
      </CardFooter>
    </FamilyCard>
  );
}

function FamilyTableView({ families }: { families: FamilyDirectoryRecord[] }) {
  return (
    <TablePanel $accent="cyan">
      <TableScroller>
        <Table>
          <thead>
            <tr>
              <th>Family record</th>
              <th>Contact</th>
              <th>Active children</th>
              <th>Status</th>
              <th>Added</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {families.map((family) => {
              const contact = family.primary_contact;
              const children = family.active_children;
              const additionalChildren = Math.max(0, family.active_child_count - Math.min(2, children.length));
              return (
                <tr key={family.id}>
                  <td>
                    <FamilyCell>
                      <FamilyAvatar><UserGroupIcon aria-hidden="true" /></FamilyAvatar>
                      <div><strong><NameLink to={`/families/${encodeURIComponent(family.id)}`}>{family.name}</NameLink></strong><small>{family.file_number ? `File ${family.file_number}` : 'No file number'}</small></div>
                    </FamilyCell>
                  </td>
                  <td><ContactCell><strong>{contact ? `${contact.first_name} ${contact.last_name}` : 'No primary contact listed'}</strong><small>{contact?.email || contact?.cell_phone || 'No contact details'}</small></ContactCell></td>
                  <td>
                    <ChildrenCell>
                      {children.length === 0 && <ChildPill>{family.active_child_count ? `${family.active_child_count} active` : 'None active'}</ChildPill>}
                      {children.slice(0, 2).map((child) => <ChildPillLink key={child.id} to={`/children/${encodeURIComponent(child.id)}`}>{child.first_name}<em>{child.age_group || 'Unspecified'}</em></ChildPillLink>)}
                      {additionalChildren > 0 && <ChildPill>+{additionalChildren}</ChildPill>}
                    </ChildrenCell>
                  </td>
                  <td><StatusChip $tone={statusTone(family.status)}>{titleCase(family.status)}</StatusChip></td>
                  <td>{formatDate(family.created_at)}</td>
                  <td><ProfileLink to={`/families/${encodeURIComponent(family.id)}`}>Open profile</ProfileLink></td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      </TableScroller>
    </TablePanel>
  );
}

function LoadingCards() {
  return (
    <SkeletonGrid aria-label="Loading family records" aria-busy="true">
      {Array.from({ length: 6 }, (_, index) => (
        <SkeletonCard key={index}>
          <SkeletonLine $width="48%" $height="18px" />
          <SkeletonLine $width="28%" />
          <SkeletonLine $width="100%" $height="70px" />
          <SkeletonLine $width="68%" />
          <SkeletonLine $width="84%" />
        </SkeletonCard>
      ))}
    </SkeletonGrid>
  );
}

export default function FamiliesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const session = useSession();
  const canManageFamilies = hasPermission(session.user, ACCESS.childcareManage);
  const organizationId = session.user?.organization_id || null;
  const organizationBoundary = resolveFamilyOrganizationBoundary({
    sessionStatus: session.status,
    identityOrganizationId: organizationId,
    loadedOrganizationId: session.organization?.id || null,
    organizationUnavailable: session.organizationUnavailable,
  });
  const canReadFamilies = organizationBoundary === 'ready';
  const [queryInput, setQueryInput] = useState('');
  const deferredQuery = useDeferredValue(queryInput.trim());
  const [statusFilter, setStatusFilter] = useState('all');
  const [offset, setOffset] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>('cards');
  const [drawerRequest, setDrawerRequest] = useState<FamilyDrawerRequest | null>(null);
  const [savedMessage, setSavedMessage] = useState('');
  const directoryQuery = useMemo(() => ({
    search: deferredQuery,
    status: statusFilter === 'all' ? '' : statusFilter,
    limit: 50,
    offset,
  }), [deferredQuery, offset, statusFilter]);
  const familiesState = useFamilies(organizationId, canReadFamilies, directoryQuery);

  const directory = familiesState.data?.directory;
  const families = directory?.items || [];
  const stats = familiesState.data?.stats;
  const organizationName = canReadFamilies ? session.organization?.name || 'Authenticated organization' : null;
  const totalMatches = directory?.total || 0;
  const currentPage = directory ? Math.floor(directory.offset / directory.limit) + 1 : 1;
  const totalPages = directory ? Math.max(1, Math.ceil(directory.total / directory.limit)) : 1;

  const hasFilters = queryInput.trim().length > 0 || statusFilter !== 'all';
  const requestedAction = searchParams.get('action');
  const requestedMode = searchParams.get('mode');

  useEffect(() => {
    if (!canReadFamilies || requestedAction !== 'register' || drawerRequest) return;
    if (canManageFamilies) setDrawerRequest({ mode: 'create', entry: requestedMode === 'intake' ? 'intake' : 'directory' });
    const next = new URLSearchParams(searchParams);
    next.delete('action');
    next.delete('mode');
    setSearchParams(next, { replace: true });
  }, [canManageFamilies, canReadFamilies, drawerRequest, requestedAction, requestedMode, searchParams, setSearchParams]);

  useEffect(() => {
    setOffset(0);
  }, [deferredQuery]);

  useEffect(() => {
    if (!directory || directory.total === 0 || directory.offset < directory.total) return;
    setOffset(Math.max(0, Math.floor((directory.total - 1) / directory.limit) * directory.limit));
  }, [directory]);

  const clearFilters = () => {
    setQueryInput('');
    setStatusFilter('all');
    setOffset(0);
  };

  const finishMutation = (message: string) => {
    setSavedMessage(message);
    setDrawerRequest(null);
    familiesState.retry();
  };

  let content;
  if (organizationBoundary === 'checking-session') {
    content = (
      <StatePanel $accent="cyan">
        <StateCopy><Spinner /><h2>Checking the secure session.</h2><p>No family request is sent until the authenticated identity and organization boundary are known.</p></StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'session-unavailable') {
    content = (
      <StatePanel $accent="amber" role="alert">
        <StateCopy>
          <ShieldCheckIcon />
          <StatusChip $tone="warning">Session check unavailable</StatusChip>
          <h2>The secure session could not be verified.</h2>
          <p>No family request was sent. Retry the identity check before reading organization records.</p>
          <ActionButton type="button" onClick={session.retry}><ArrowPathIcon /> Retry secure session</ActionButton>
        </StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'anonymous') {
    content = (
      <StatePanel $accent="plasma">
        <StateCopy>
          <LockClosedIcon />
          <StatusChip $tone="warning">Session required</StatusChip>
          <h2>Connect before opening family records.</h2>
          <p>This page does not display invented preview families. Sign in to read the organization-scoped directory from FastAPI.</p>
          <SessionLink to="/login">Connect secure session</SessionLink>
        </StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'organization-required') {
    content = (
      <StatePanel $accent="amber">
        <StateCopy>
          <ShieldCheckIcon />
          <StatusChip $tone="warning">Organization required</StatusChip>
          <h2>Family reads are intentionally blocked.</h2>
          <p>The authenticated identity has no organization ID. CareSync will not call an endpoint that could return unscoped records.</p>
        </StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'organization-loading') {
    content = (
      <StatePanel $accent="cyan" aria-busy="true">
        <StateCopy><Spinner /><h2>Confirming the organization boundary.</h2><p>The identity is authenticated, but family reads remain blocked until organization metadata loads and matches it.</p></StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'organization-unavailable') {
    content = (
      <StatePanel $accent="amber" role="alert">
        <StateCopy>
          <ShieldCheckIcon />
          <StatusChip $tone="warning">Organization metadata unavailable</StatusChip>
          <h2>The family boundary could not be confirmed.</h2>
          <p>No family request was sent because the organization record is unavailable.</p>
          <ActionButton type="button" onClick={session.retry}><ArrowPathIcon /> Retry organization connection</ActionButton>
        </StateCopy>
      </StatePanel>
    );
  } else if (organizationBoundary === 'organization-mismatch') {
    content = (
      <StatePanel $accent="amber" role="alert">
        <StateCopy>
          <ShieldCheckIcon />
          <StatusChip $tone="warning">Organization mismatch</StatusChip>
          <h2>The family directory is safely locked.</h2>
          <p>The authenticated identity and loaded organization metadata do not agree. No family request was sent.</p>
          <ActionButton type="button" onClick={session.retry}><ArrowPathIcon /> Recheck organization boundary</ActionButton>
        </StateCopy>
      </StatePanel>
    );
  } else if (familiesState.status === 'loading' || familiesState.status === 'idle') {
    content = <LoadingCards />;
  } else if (familiesState.status === 'error') {
    content = (
      <StatePanel $accent="amber">
        <StateCopy>
          <ShieldCheckIcon />
          <StatusChip $tone="warning">Live request failed</StatusChip>
          <h2>The family directory is unavailable.</h2>
          <p>{familiesState.error}. No fallback or sample records are being shown.</p>
          <ActionButton type="button" onClick={familiesState.retry}><ArrowPathIcon /> Retry family request</ActionButton>
        </StateCopy>
      </StatePanel>
    );
  } else if (families.length === 0 && !hasFilters && totalMatches === 0) {
    content = (
      <StatePanel $accent="cyan">
        <StateCopy>
          <UserGroupIcon />
          <StatusChip $tone="info">Live response · 0 records</StatusChip>
          <h2>No family records were returned.</h2>
          <p>Start the organization directory by registering the first family.</p>
          <ActionButton type="button" $variant="primary" onClick={() => setDrawerRequest({ mode: 'create' })}><PlusIcon /> Register family</ActionButton>
        </StateCopy>
      </StatePanel>
    );
  } else {
    content = (
      <>
        <Metrics aria-label="Family directory summary">
          <Metric $accent="plasma"><MetricHeader><UserGroupIcon /><span>Live total</span></MetricHeader><MetricValue><strong>{stats?.families ?? '—'}</strong><small>Family records in this organization</small></MetricValue></Metric>
          <Metric $accent="cyan"><MetricHeader><CheckBadgeIcon /><span>Active</span></MetricHeader><MetricValue><strong>{stats?.active_families ?? '—'}</strong><small>Families marked active</small></MetricValue></Metric>
          <Metric $accent="amber"><MetricHeader><ClockIcon /><span>Pending</span></MetricHeader><MetricValue><strong>{stats?.pending_families ?? '—'}</strong><small>Families awaiting completion</small></MetricValue></Metric>
          <Metric $accent="cyan"><MetricHeader><UsersIcon /><span>Children</span></MetricHeader><MetricValue><strong>{stats?.active_children ?? '—'}</strong><small>Active children across family records</small></MetricValue></Metric>
        </Metrics>

        {!stats && (
          <ReadOnlyNotice role="status">
            <ArrowPathIcon aria-hidden="true" />
            <span><strong>The family directory is connected.</strong> Summary metrics are temporarily unavailable; the live organization records below remain usable.</span>
          </ReadOnlyNotice>
        )}

        <Controls $accent="plasma">
          <Field>
            <span>Search organization records</span>
            <InputShell>
              <MagnifyingGlassIcon aria-hidden="true" />
              <input
                type="search"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="Family, primary contact, active child, file number…"
                aria-label="Search family records"
              />
            </InputShell>
          </Field>
          <Field>
            <span>Family status</span>
            <Select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setOffset(0); }} aria-label="Filter families by status">
              <option value="all">All statuses</option>
              <option value="active">Active</option>
              <option value="pending">Pending</option>
              <option value="inactive">Inactive</option>
              <option value="archived">Archived</option>
            </Select>
          </Field>
          <Field>
            <span>Roster layout</span>
            <ViewPicker aria-label="Choose family roster layout">
              <ViewButton type="button" $active={viewMode === 'cards'} aria-pressed={viewMode === 'cards'} onClick={() => setViewMode('cards')}><Squares2X2Icon /> Cards</ViewButton>
              <ViewButton type="button" $active={viewMode === 'table'} aria-pressed={viewMode === 'table'} onClick={() => setViewMode('table')}><TableCellsIcon /> Table</ViewButton>
            </ViewPicker>
          </Field>
        </Controls>

        <ResultHeader>
          <div>
            <strong>{families.length} of {totalMatches} matching {totalMatches === 1 ? 'family' : 'families'} shown</strong>
            <p>
              Search, status, and paging run on the server; this screen receives only a minimized directory page.
              {directory && families.length > 0 ? ` Showing ${directory.offset + 1}–${Math.min(directory.offset + families.length, directory.total)}.` : ''}
            </p>
          </div>
          {hasFilters && <ActionButton type="button" onClick={clearFilters}>Clear search and status</ActionButton>}
        </ResultHeader>

        {families.length === 0 ? (
          <EmptyResults $accent="amber">
            <StateCopy><MagnifyingGlassIcon /><h2>No server records match.</h2><p>Try a different family, primary contact, active child, file number, or status.</p><ActionButton type="button" onClick={clearFilters}>Clear filters</ActionButton></StateCopy>
          </EmptyResults>
        ) : viewMode === 'cards' ? (
          <Cards>{families.map((family) => <FamilyCardView key={family.id} family={family} />)}</Cards>
        ) : (
          <FamilyTableView families={families} />
        )}
        {directory && directory.total > directory.limit && (
          <Pagination aria-label="Family directory pages">
            <ActionButton type="button" disabled={directory.offset === 0} onClick={() => setOffset(Math.max(0, directory.offset - directory.limit))}>Previous</ActionButton>
            <span>Page {currentPage} of {totalPages}</span>
            <ActionButton type="button" disabled={directory.offset + directory.limit >= directory.total} onClick={() => setOffset(directory.offset + directory.limit)}>Next</ActionButton>
          </Pagination>
        )}
      </>
    );
  }

  return (
    <Page>
      <PageHeader>
        <div>
          <Eyebrow><IdentificationIcon width={14} /> Care network · family directory</Eyebrow>
          <h1>Families, in clear orbit.</h1>
          <p>Register households, review the care network, update legacy profile markers, and archive records inside the confirmed tenant boundary.</p>
        </div>
        <HeaderStatus>
          <StatusChip $tone={canReadFamilies ? 'success' : 'neutral'}>{canReadFamilies ? 'Live family records' : 'Data link inactive'}</StatusChip>
          <small>{canReadFamilies ? organizationName : 'A confirmed organization context is required.'}</small>
          {canReadFamilies && <ActionButton type="button" $variant="primary" onClick={() => setDrawerRequest({ mode: 'create' })}><PlusIcon /> Register family</ActionButton>}
        </HeaderStatus>
      </PageHeader>

      <ReadOnlyNotice role={savedMessage ? 'status' : undefined} aria-live="polite"><ShieldCheckIcon aria-hidden="true" /><span><strong>{savedMessage || 'Dedicated Basic family workflow.'}</strong> {savedMessage ? 'The organization directory is refreshing now.' : 'Create, view, edit, and archive operations use organization-scoped transactional endpoints.'}</span></ReadOnlyNotice>

      {content}
      {drawerRequest && canReadFamilies && organizationId && <FamilyDrawer request={drawerRequest} organizationId={organizationId} onClose={() => setDrawerRequest(null)} onSaved={finishMutation} />}
    </Page>
  );
}
