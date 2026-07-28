import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { ActionButton, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useMotion } from '../../motion';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import { featureIntegrationManifest } from '../../realtime/featureIntegrationManifest';
import { familyAuthorityDecisionPath, type ChildAuthorityRouteFocus } from './childAuthorityFocus';
import {
  ChildAuthoritySummaryApiError,
  fetchChildAuthoritySummary,
  isChildAuthoritySummaryUnavailable,
  type ChildAuthoritySummary,
  type ChildAuthoritySummaryRecord,
} from './childAuthoritySummaryApi';

const Panel = styled(GlassPanel)`
  display: grid;
  gap: 15px;
  padding: 19px;
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.08rem; font-weight: 550; letter-spacing: -.03em; }
  p { max-width: 780px; margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.55; }
  > svg { width: 22px; color: ${({ theme }) => theme.color.cyan}; }
`;

const Banner = styled.div<{ $warning?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 13px;
  border: 1px solid ${({ $warning, theme }) => $warning ? theme.color.amber : theme.color.cyan};
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $warning, theme }) => `color-mix(in srgb, ${$warning ? theme.color.amber : theme.color.cyan} 7%, ${theme.color.surfaceStrong})`};
  font-size: .72rem;
  line-height: 1.55;
  svg { width: 17px; flex: 0 0 auto; color: ${({ $warning, theme }) => $warning ? theme.color.amber : theme.color.cyan}; }
`;

const SummaryBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: .72rem;
  color: ${({ theme }) => theme.color.textMuted};
`;

const RecordGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  @media (max-width: 980px) { grid-template-columns: 1fr; }
`;

const RecordCard = styled.article<{ $focused?: boolean }>`
  display: grid;
  gap: 9px;
  min-width: 0;
  padding: 13px;
  border: 1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.border};
  border-radius: 14px 6px 14px 6px;
  outline: none;
  background: ${({ $focused, theme }) => $focused ? `color-mix(in srgb, ${theme.color.cyan} 8%, ${theme.color.surfaceStrong})` : theme.color.surfaceStrong};
  box-shadow: ${({ $focused, theme }) => $focused ? theme.shadow.cyan : 'none'};
  h3 { margin: 0; font-size: .79rem; font-weight: 600; overflow-wrap: anywhere; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; overflow-wrap: anywhere; }
  > div { display: flex; flex-wrap: wrap; gap: 6px; }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 3px; }
`;

const Empty = styled.div`
  padding: 17px;
  border: 1px dashed ${({ theme }) => theme.color.controlBorder};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .73rem;
  line-height: 1.6;
  text-align: center;
`;

const ManageLink = styled(Link)`
  color: ${({ theme }) => theme.color.cyan};
  font-size: .72rem;
  font-weight: 600;
`;

function label(value: string): string {
  return value
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .replace(/\bId\b/g, 'ID');
}

function windowLabel(record: ChildAuthoritySummaryRecord): string {
  const start = new Date(record.effective_from).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
  const end = new Date(record.effective_until).toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
  return `${start} to ${end}`;
}

function recordTitle(record: ChildAuthoritySummaryRecord): string {
  if (record.record_type === 'release_authorization') return `Release recipient · ${record.recipient.display_name}`;
  if (record.record_type === 'release_rule') return `Release rule · ${label(record.safe_explanation_code)}`;
  return `${label(record.purpose_code)} · ${label(record.decision)}`;
}

function recordDescription(record: ChildAuthoritySummaryRecord): string {
  if (record.record_type === 'release_authorization') return `${label(record.recipient.relationship_kind)} · configured identity check: ${label(record.verification_policy_code)}${record.recipient.status === 'retired' ? ' · retired identity' : ''}`;
  if (record.record_type === 'release_rule') return record.scoped_person ? `Applies to ${record.scoped_person.display_name}${record.scoped_person.status === 'retired' ? ' · retired identity' : ''}` : 'Applies to all recipients';
  return `${record.policy.title} · policy version ${record.policy.version_number}`;
}

function statusTone(record: ChildAuthoritySummaryRecord): 'success' | 'warning' | 'neutral' {
  if (record.effective_status === 'supporting_evidence_unavailable') return 'warning';
  if (!record.effective_now) return 'neutral';
  if (record.record_type === 'release_authorization' && record.recipient.status === 'retired') return 'warning';
  if (record.record_type === 'release_rule' && record.scoped_person?.status === 'retired') return 'warning';
  if (record.record_type === 'release_rule') return 'warning';
  if (record.record_type === 'consent' && record.decision === 'declined') return 'warning';
  return 'success';
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ChildAuthoritySummaryApiError) return caught.message;
  return caught instanceof Error ? caught.message : 'The child authority summary could not be loaded.';
}

export default function ChildAuthoritySummaryPanel({
  childId,
  familyId,
  organizationId,
  routeFocus,
}: {
  childId: string;
  familyId: string;
  organizationId: string;
  routeFocus: ChildAuthorityRouteFocus;
}) {
  const { motionAllowed } = useMotion();
  const [summary, setSummary] = useState<ChildAuthoritySummary | null>(null);
  const [phase, setPhase] = useState<'loading' | 'ready' | 'unavailable' | 'error'>('loading');
  const [message, setMessage] = useState(routeFocus.message || '');
  const focusedCard = useRef<HTMLElement>(null);
  const requestGeneration = useRef(0);

  const load = useCallback(async (signal?: AbortSignal, initial = false) => {
    const generation = ++requestGeneration.current;
    const isCurrent = () => requestGeneration.current === generation && !signal?.aborted;
    const fail = (caught: unknown): boolean => {
      if (!isCurrent()) return true;
      if (isChildAuthoritySummaryUnavailable(caught)) {
        setSummary(null);
        setMessage('The verified authority summary is not enabled for this deployment yet. The child profile remains available.');
        setPhase('unavailable');
        return true;
      }
      setSummary(null);
      setMessage(errorMessage(caught));
      setPhase('error');
      return initial;
    };
    if (initial && isCurrent()) {
      setSummary(null);
      setMessage(routeFocus.message || '');
      setPhase('loading');
    }
    try {
      const result = await fetchChildAuthoritySummary(childId, familyId, organizationId, routeFocus.focus, signal);
      if (!isCurrent()) return;
      setSummary(result);
      setMessage(routeFocus.message || '');
      setPhase('ready');
    } catch (caught) {
      if (!isCurrent() || (caught instanceof DOMException && caught.name === 'AbortError')) return;
      if (caught instanceof ChildAuthoritySummaryApiError && caught.code === 'child_authority_focus_not_found') {
        try {
          const current = await fetchChildAuthoritySummary(childId, familyId, organizationId, null, signal);
          if (!isCurrent()) return;
          setSummary(current);
          setMessage(`${caught.message} Current child authority facts are shown without substituting another target.`);
          setPhase('ready');
        } catch (fallbackCaught) {
          if (!isCurrent() || (fallbackCaught instanceof DOMException && fallbackCaught.name === 'AbortError')) return;
          if (!fail(fallbackCaught)) throw fallbackCaught;
        }
        return;
      }
      if (!fail(caught)) throw caught;
    }
  }, [childId, familyId, organizationId, routeFocus.focus, routeFocus.message]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal, true);
    return () => {
      controller.abort();
      requestGeneration.current += 1;
    };
  }, [load]);

  useRealtimeRefresh({
    scope: 'child-authority-summary',
    organizationId,
    enabled: phase !== 'unavailable',
    entityTypes: featureIntegrationManifest.children.realtimeEntities,
    refresh: async () => load(undefined, false),
  });

  const records = useMemo(() => summary ? [
    ...summary.release_authorizations,
    ...summary.release_rules,
    ...summary.consent_decisions,
  ] : [], [summary]);

  useEffect(() => {
    if (!summary?.focus || !focusedCard.current) return;
    const frame = window.requestAnimationFrame(() => {
      focusedCard.current?.scrollIntoView({ behavior: motionAllowed ? 'smooth' : 'auto', block: 'center' });
      focusedCard.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [motionAllowed, summary?.focus?.id, summary?.focus?.record_type]);

  const visibleRecords = summary?.focus
    ? [summary.focus, ...records.filter((record) => record.id !== summary.focus?.id || record.record_type !== summary.focus?.record_type)]
    : records;

  return <Panel $accent="cyan" aria-live="polite">
    <Header><div><h2>Authority & consent summary</h2><p>Minimum-necessary administrative facts for this child. Contact details, evidence, signer provenance, confidential reasons, and policy content stay in the private family workspace.</p></div><ShieldCheckIcon /></Header>
    <Banner $warning><ExclamationTriangleIcon /><span>This is not checkout permission. Staff release must always be re-evaluated from fresh attendance and authority context at the moment of checkout.</span></Banner>
    {message && <Banner $warning={phase !== 'ready'} role={phase === 'error' ? 'alert' : 'status'}><ExclamationTriangleIcon /><span>{message}</span></Banner>}
    {phase === 'loading' && <Empty>Loading the current child authority revision…</Empty>}
    {phase === 'unavailable' && <Empty>The verified authority summary is not enabled for this deployment.</Empty>}
    {phase === 'error' && <Empty><p>{message}</p><ActionButton type="button" onClick={() => void load(undefined, true)}><ArrowPathIcon /> Try again</ActionButton></Empty>}
    {phase === 'ready' && summary && <>
      <SummaryBar><span><strong>Revision {summary.authority_revision}</strong> · {summary.reviewed ? 'authority activity recorded' : 'no versioned authority activity yet'} · generated {new Date(summary.generated_at).toLocaleString('en-CA')}</span><ManageLink to={`/families/${encodeURIComponent(familyId)}`}>Manage private family authority →</ManageLink></SummaryBar>
      {visibleRecords.length ? <RecordGrid>{visibleRecords.map((record) => {
        const isFocused = summary.focus?.id === record.id && summary.focus.record_type === record.record_type;
        return <RecordCard key={`${record.record_type}:${record.id}`} ref={isFocused ? focusedCard : undefined} tabIndex={isFocused ? -1 : undefined} $focused={isFocused} aria-label={isFocused ? `Receipt target: ${recordTitle(record)}` : undefined}>
          <div><StatusChip $tone={statusTone(record)}>{label(record.effective_status)}</StatusChip>{isFocused && <StatusChip $tone="info"><IdentificationIcon width={13} /> Receipt target</StatusChip>}</div>
          <h3>{recordTitle(record)}</h3><p>{recordDescription(record)}</p><p>{windowLabel(record)}</p>
          <ManageLink to={familyAuthorityDecisionPath(familyId, { kind: record.record_type, id: record.id })}>Open exact private record →</ManageLink>
        </RecordCard>;
      })}</RecordGrid> : <Empty><CheckCircleIcon width={18} /> No current or scheduled versioned release or consent records are present for this child.</Empty>}
    </>}
  </Panel>;
}
