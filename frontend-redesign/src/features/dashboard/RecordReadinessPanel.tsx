import {
  CheckCircleIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
  ShieldExclamationIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { GlassPanel, StatusChip } from '../../components/ui/Primitives';
import type { ResourceStatus } from '../../hooks/useCommandData';
import type { ChildRecordReadinessItem, ChildRecordReadinessResponse, ChildRecordReadinessSeverity } from './readinessApi';

const Panel = styled(GlassPanel)`
  display: grid;
  gap: 0;
  overflow: hidden;
  border-radius: ${({ theme }) => theme.radius.md};
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 19px 20px 16px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; font-weight: 540; letter-spacing: -.025em; }
  p { margin: 5px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.55; }

  @media (max-width: 540px) { flex-direction: column; }
`;

const Counts = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
  @media (max-width: 540px) { justify-content: flex-start; }
`;

const List = styled.ul`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const ListItem = styled.li`
  min-width: 0;
  & + & { border-top: 1px solid ${({ theme }) => theme.color.border}; }
`;

const ItemLink = styled(Link)<{ $severity: ChildRecordReadinessSeverity }>`
  display: grid;
  min-width: 0;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 76px;
  padding: 13px 20px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  transition: background ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};

  &:hover { background: ${({ theme }) => theme.color.surfaceHover}; transform: translateX(2px); }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: -3px; }
  > svg:first-child { width: 21px; color: ${({ $severity, theme }) => $severity === 'critical' ? theme.color.coral : $severity === 'warning' ? theme.color.amber : theme.color.cyan}; }
  > svg:last-child { width: 17px; color: ${({ theme }) => theme.color.textMuted}; }
  strong { display: block; color: ${({ theme }) => theme.color.text}; font-size: .8rem; font-weight: 600; }
  span { display: block; margin-top: 4px; color: ${({ theme }) => theme.color.textMuted}; font-size: .74rem; line-height: 1.5; }

  @media (max-width: 440px) { padding-inline: 14px; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 9px; }
`;

const ActionHint = styled.span`
  && { margin-top: 7px; color: ${({ theme }) => theme.color.cyan}; font-size: .69rem; font-weight: 600; }
`;

const State = styled.div`
  display: grid;
  min-height: 126px;
  place-items: center;
  padding: 24px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  text-align: center;
  div { max-width: 520px; }
  svg { width: 28px; margin: 0 auto 9px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; color: ${({ theme }) => theme.color.text}; font-size: .82rem; }
  p { margin: 5px 0 0; font-size: .75rem; line-height: 1.55; }
`;

export interface RecordReadinessPanelProps {
  status: ResourceStatus;
  data: ChildRecordReadinessResponse | null;
  message?: string;
}

function tone(value: number, severity: ChildRecordReadinessSeverity): 'warning' | 'info' | 'neutral' {
  if (value === 0) return 'neutral';
  if (severity === 'critical') return 'warning';
  if (severity === 'warning') return 'warning';
  return 'info';
}

export function readinessActionLabel(item: ChildRecordReadinessItem): string {
  if (item.action_route.startsWith('/families/') && item.action_route.includes('focus=family-status')) return 'Open family status review';
  if (item.action_route.startsWith('/rooms?')) return 'Select and approve a room';
  if (item.action_route.startsWith('/children/')) return 'Open the affected child record';
  if (item.action_route.startsWith('/families/')) return 'Open the affected family record';
  return 'Open the exact review';
}

export default function RecordReadinessPanel({ status, data, message }: RecordReadinessPanelProps) {
  const loading = status === 'loading' || status === 'idle';
  return (
    <Panel as="section" aria-labelledby="record-readiness-title" aria-busy={loading}>
      <Header>
        <div>
          <h2 id="record-readiness-title">Record readiness</h2>
          <p>Prioritized review signals from canonical family, child, enrollment, and room facts.</p>
        </div>
        {data && <Counts aria-label={`${data.total} readiness items`}>
          <StatusChip $tone={tone(data.counts.critical, 'critical')}>{data.counts.critical} critical</StatusChip>
          <StatusChip $tone={tone(data.counts.warning, 'warning')}>{data.counts.warning} warning</StatusChip>
          {data.counts.info > 0 && <StatusChip $tone="info">{data.counts.info} info</StatusChip>}
        </Counts>}
      </Header>
      {status === 'error' ? (
        <State role="alert"><div><ShieldExclamationIcon /><strong>Readiness queue unavailable</strong><p>{message || 'Refresh after the connection returns.'}</p></div></State>
      ) : loading ? (
        <State><div><p>Checking record readiness…</p></div></State>
      ) : !data || data.total === 0 ? (
        <State><div><CheckCircleIcon /><strong>No current review signals</strong><p>This is an operational queue, not a legal-compliance certification.</p></div></State>
      ) : (
        <>
          <List aria-label="Records requiring review">
            {data.items.map((item) => (
              <ListItem key={item.key}>
                <ItemLink to={item.action_route} $severity={item.severity}>
                  <ExclamationTriangleIcon aria-hidden="true" />
                  <div><strong>{item.title}</strong><span>{item.message}</span><ActionHint>{readinessActionLabel(item)}</ActionHint></div>
                  <ChevronRightIcon aria-hidden="true" />
                </ItemLink>
              </ListItem>
            ))}
          </List>
          {data.total > data.items.length && <State><div><p>Showing {data.items.length} highest-priority records from {data.total} current signals.</p></div></State>}
        </>
      )}
    </Panel>
  );
}
