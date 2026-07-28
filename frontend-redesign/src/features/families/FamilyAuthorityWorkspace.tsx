import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  DocumentCheckIcon,
  DocumentMagnifyingGlassIcon,
  ExclamationTriangleIcon,
  IdentificationIcon,
  PencilSquareIcon,
  PlusIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserGroupIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { createClientOperationId } from '../../api/childcareCommand';
import { useSession } from '../../auth/SessionContext';
import {
  ChildcareCommandRecoveredCommitError,
  childcareMutationControlDisabled,
  useChildcareCommandRecovery,
  type ChildcareMutationMetadata,
} from '../../childcare-commands/ChildcareCommandRecoveryContext';
import { ActionButton, Eyebrow, GlassPanel, IconButton, StatusChip } from '../../components/ui/Primitives';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import type { FamilyDetailRecord } from './types';
import {
  createAuthorityPerson,
  FamilyAuthorityApiError,
  fetchAuthorityEvidenceObjectContent,
  fetchFamilyAuthorityWorkspace,
  invalidateAuthorityEvidence,
  isFamilyAuthorityUnavailable,
  recordAuthorityEvidence,
  rejectAuthorityEvidence,
  replaceAuthorityPerson,
  retireAuthorityPerson,
  reviewAuthorityEvidence,
  scanAuthorityEvidenceObject,
  supersedeAuthorityEvidence,
  uploadAuthorityEvidenceObject,
} from './familyAuthorityApi';
import {
  attachableEvidenceObjects,
  AUTHORITY_EVIDENCE_KINDS,
  AUTHORITY_RELATIONSHIPS,
  authorityLabel,
  authorityPersonSourceOptions,
  authorityWorkspaceTabForFocus,
  authorityWorkspaceCounts,
  authorityWorkspaceFocusExists,
  DOCUMENT_EVIDENCE_KINDS,
  emptyAuthorityPersonFacts,
  evidenceActions,
  evidenceReviewAssignment,
  evidenceObjectCanScan,
  INVALIDATION_REASONS,
  normalizedAuthorityFacts,
  parseAuthorityDeepLink,
  isAuthorityDecisionFocus,
  REJECTION_REASONS,
  reviewEpistemicOptions,
  reviewedReplacementEvidence,
  shouldClearAuthorityFocusForTabSelection,
  validateAuthorityPersonFacts,
  type AuthorityWorkspaceTab,
} from './familyAuthorityModel';
import type {
  AuthorityEvidence,
  AuthorityEvidenceEpistemicStatus,
  AuthorityEvidenceInvalidationReason,
  AuthorityEvidenceKind,
  AuthorityEvidenceObject,
  AuthorityEvidenceRejectionReason,
  AuthorityPerson,
  AuthorityPersonFacts,
  FamilyAuthorityWorkspaceRecord,
} from './familyAuthorityTypes';
import FamilyAuthorityDecisionPanel from './FamilyAuthorityDecisionPanel';

const Panel = styled(GlassPanel)`
  display: grid;
  gap: 16px;
  padding: 19px;
`;
const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  h2 { margin: 7px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: 1.2rem; font-weight: 550; letter-spacing: -.03em; }
  p { max-width: 760px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .74rem; line-height: 1.6; }
  @media (max-width: 680px) { flex-direction: column; }
`;
const Warning = styled.div<{ $error?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 12px 13px;
  border: 1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.amber};
  border-radius: 12px 5px 12px 5px;
  outline: 0;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $error, theme }) => `color-mix(in srgb, ${$error ? theme.color.coral : theme.color.amber} 8%, ${theme.color.surfaceStrong})`};
  font-size: .73rem;
  line-height: 1.55;
  svg { width: 18px; flex: 0 0 auto; color: ${({ $error, theme }) => $error ? theme.color.coral : theme.color.amber}; }
`;
const Success = styled(Warning)`border-color: ${({ theme }) => theme.color.mint}; background: color-mix(in srgb, ${({ theme }) => theme.color.mint} 8%, ${({ theme }) => theme.color.surfaceStrong}); svg { color: ${({ theme }) => theme.color.mint}; }`;
const Metrics = styled.div`display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 9px;`;
const Metric = styled.div`
  padding: 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  background: ${({ theme }) => theme.color.surfaceStrong};
  span { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; letter-spacing: .07em; text-transform: uppercase; }
  strong { display: block; margin-top: 6px; font-family: 'CareSync Display', sans-serif; font-size: 1.25rem; font-weight: 540; }
`;
const Tabs = styled.div`display: flex; flex-wrap: wrap; gap: 7px;`;
const Tab = styled.button<{ $active: boolean }>`
  min-height: 42px; padding: 0 13px; border: 1px solid ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.controlBorder}; border-radius: 11px 5px 11px 5px; color: ${({ theme }) => theme.color.textSoft}; background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.cyan} 9%, ${theme.color.control})` : theme.color.control}; cursor: pointer; font: inherit; font-size: .74rem; font-weight: 600;
`;
const Section = styled.section`display: grid; gap: 10px;`;
const SectionHead = styled.header`
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .95rem; font-weight: 550; }
  p { margin: 3px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.5; }
  @media (max-width: 560px) { align-items: stretch; flex-direction: column; }
`;
const Cards = styled.div`display: grid; gap: 9px;`;
const Card = styled.article<{ $focused?: boolean }>`
  display: grid; gap: 10px; padding: 13px; border: 1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.border}; border-radius: 14px 6px 14px 6px; outline: 0; background: ${({ $focused, theme }) => $focused ? `color-mix(in srgb, ${theme.color.cyan} 7%, ${theme.color.surfaceStrong})` : theme.color.surfaceStrong}; box-shadow: ${({ $focused, theme }) => $focused ? theme.shadow.cyan : 'none'};
`;
const CardTop = styled.div`
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  strong { display: block; font-size: .8rem; font-weight: 620; }
  small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.5; overflow-wrap: anywhere; }
`;
const CardActions = styled.div`display: flex; flex-wrap: wrap; gap: 7px;`;
const Empty = styled.div`padding: 17px; border: 1px dashed ${({ theme }) => theme.color.controlBorder}; border-radius: 12px; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.6; text-align: center;`;
const State = styled.div`display: grid; min-height: 220px; place-items: center; padding: 24px; text-align: center; div { max-width: 540px; } svg { width: 36px; margin: 0 auto 10px; color: ${({ theme }) => theme.color.cyan}; } h3 { margin: 0 0 7px; font-size: 1rem; } p { margin: 0 0 14px; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.65; }`;
const Backdrop = styled.div`position: fixed; z-index: 1500; inset: 0; display: grid; place-items: center; padding: 18px; background: ${({ theme }) => theme.color.overlay}; backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});`;
const DialogSurface = styled(GlassPanel)`display: grid; width: min(720px, 100%); max-height: calc(100dvh - 36px); grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; outline: 0;`;
const DialogHeader = styled.header`display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 19px; border-bottom: 1px solid ${({ theme }) => theme.color.divider}; h2 { margin: 7px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: 1.3rem; font-weight: 550; } p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.55; }`;
const DialogBody = styled.div`display: grid; align-content: start; gap: 13px; overflow-y: auto; padding: 18px 19px;`;
const DialogFooter = styled.footer`display: flex; justify-content: flex-end; gap: 8px; padding: 14px 19px; border-top: 1px solid ${({ theme }) => theme.color.divider}; @media (max-width: 480px) { display: grid; grid-template-columns: 1fr 1fr; }`;
const Grid = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 11px; @media (max-width: 560px) { grid-template-columns: 1fr; }`;
const Field = styled.label<{ $wide?: boolean }>`display: grid; gap: 6px; min-width: 0; ${({ $wide }) => $wide ? 'grid-column: 1 / -1;' : ''} > span { color: ${({ theme }) => theme.color.textSoft}; font-size: .7rem; font-weight: 600; } input, select, textarea { width: 100%; min-height: 44px; padding: 0 11px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 10px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .78rem; } textarea { min-height: 88px; padding-top: 10px; resize: vertical; } input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 15%, transparent); } [aria-invalid='true'] { border-color: ${({ theme }) => theme.color.coral}; } small { color: ${({ theme }) => theme.color.coral}; font-size: .68rem; }`;
const FinePrint = styled.p`margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.6;`;

type Phase = 'loading' | 'ready' | 'unavailable' | 'error';
type DialogState =
  | { kind: 'person'; person: AuthorityPerson | null }
  | { kind: 'retire'; person: AuthorityPerson }
  | { kind: 'evidence'; evidence: AuthorityEvidence | null }
  | { kind: 'review'; evidence: AuthorityEvidence }
  | { kind: 'reject'; evidence: AuthorityEvidence }
  | { kind: 'invalidate'; evidence: AuthorityEvidence }
  | { kind: 'supersede'; evidence: AuthorityEvidence }
  | null;

function dateTimeLabel(value: string | null): string {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
}

function toUtc(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function errorMessage(caught: unknown): string {
  let current = caught;
  for (let depth = 0; depth < 5; depth += 1) {
    if (current instanceof FamilyAuthorityApiError) return current.message;
    if (!current || typeof current !== 'object' || !('cause' in current)) break;
    current = (current as { cause?: unknown }).cause;
  }
  if (caught instanceof Error) return caught.message;
  return 'The authority action could not be completed.';
}

function AccessibleDialog({ title, description, busy, onClose, children, footer }: { title: string; description: string; busy: boolean; onClose: () => void; children: ReactNode; footer: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose(); return; }
      if (event.key !== 'Tab' || !ref.current) return;
      const focusable = [...ref.current.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]')];
      if (!focusable.length) return;
      const first = focusable[0]; const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', keydown);
    requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus());
    return () => { document.body.style.overflow = overflow; window.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [busy, onClose]);
  return createPortal(<Backdrop onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}><DialogSurface ref={ref} role="dialog" aria-modal="true" aria-labelledby="authority-dialog-title" aria-describedby="authority-dialog-description" $accent="cyan"><DialogHeader><div><Eyebrow><ShieldCheckIcon width={14} /> Family authority</Eyebrow><h2 id="authority-dialog-title">{title}</h2><p id="authority-dialog-description">{description}</p></div><IconButton type="button" onClick={onClose} disabled={busy} aria-label="Close authority dialog"><XMarkIcon /></IconButton></DialogHeader><DialogBody>{children}</DialogBody><DialogFooter>{footer}</DialogFooter></DialogSurface></Backdrop>, document.body);
}

function PersonDialog({ detail, workspace, person, busy, error, onClose, onSubmit }: { detail: FamilyDetailRecord; workspace: FamilyAuthorityWorkspaceRecord; person: AuthorityPerson | null; busy: boolean; error: string; onClose: () => void; onSubmit: (sourceKey: string, facts: AuthorityPersonFacts) => void }) {
  const options = useMemo(() => authorityPersonSourceOptions(detail, workspace.people), [detail, workspace.people]);
  const [sourceKey, setSourceKey] = useState(person ? 'existing' : options[0]?.key || 'manual');
  const selected = options.find((option) => option.key === sourceKey) || options[0];
  const [facts, setFacts] = useState<AuthorityPersonFacts>(() => person?.current_version?.facts || selected?.facts || emptyAuthorityPersonFacts());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const update = <Key extends keyof AuthorityPersonFacts>(key: Key, value: AuthorityPersonFacts[Key]) => setFacts((current) => ({ ...current, [key]: value }));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = normalizedAuthorityFacts(facts);
    const next = validateAuthorityPersonFacts(normalized);
    setErrors(next);
    if (!Object.keys(next).length) onSubmit(sourceKey, normalized);
  };
  const title = person ? `Replace ${person.current_version?.facts.first_name || 'authority person'}’s current facts` : 'Add an authority person';
  return <AccessibleDialog title={title} description="Identity facts are versioned. Saved guardian/contact records are source references only and never become pickup authority by themselves." busy={busy} onClose={onClose} footer={<><ActionButton type="button" onClick={onClose} disabled={busy}>Cancel</ActionButton><ActionButton type="submit" form="authority-person-form" $variant="primary" disabled={busy}>{busy ? 'Saving…' : person ? 'Replace facts' : 'Add person'}</ActionButton></>}>
    <form id="authority-person-form" onSubmit={submit} noValidate>
      <Grid>
        {!person && <Field $wide><span>Identity source</span><select value={sourceKey} onChange={(event) => { const next = options.find((option) => option.key === event.target.value); setSourceKey(event.target.value); if (next) setFacts(next.facts); }}>{options.map((option) => <option key={option.key} value={option.key} disabled={option.disabled}>{option.label}{option.disabled ? ' · already linked' : ''}</option>)}</select><FinePrint>Choosing a saved record copies identity facts only. Legacy pickup markers are ignored.</FinePrint></Field>}
        <Field><span>First name *</span><input value={facts.first_name} maxLength={100} onChange={(event) => update('first_name', event.target.value)} aria-invalid={Boolean(errors.first_name)} />{errors.first_name && <small>{errors.first_name}</small>}</Field>
        <Field><span>Middle name</span><input value={facts.middle_name || ''} maxLength={100} onChange={(event) => update('middle_name', event.target.value || null)} /></Field>
        <Field><span>Last name *</span><input value={facts.last_name} maxLength={100} onChange={(event) => update('last_name', event.target.value)} aria-invalid={Boolean(errors.last_name)} />{errors.last_name && <small>{errors.last_name}</small>}</Field>
        <Field><span>Preferred name</span><input value={facts.preferred_name || ''} maxLength={100} onChange={(event) => update('preferred_name', event.target.value || null)} /></Field>
        <Field><span>Relationship *</span><select value={facts.relationship_kind} onChange={(event) => { const relationship = event.target.value as AuthorityPersonFacts['relationship_kind']; setFacts((current) => ({ ...current, relationship_kind: relationship, relationship_detail: relationship === 'other' ? current.relationship_detail : null })); }}>{AUTHORITY_RELATIONSHIPS.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field>
        {facts.relationship_kind === 'other' && <Field><span>Relationship detail *</span><input value={facts.relationship_detail || ''} maxLength={120} onChange={(event) => update('relationship_detail', event.target.value || null)} aria-invalid={Boolean(errors.relationship_detail)} />{errors.relationship_detail && <small>{errors.relationship_detail}</small>}</Field>}
        <Field><span>Email</span><input type="email" value={facts.email || ''} maxLength={320} onChange={(event) => update('email', event.target.value || null)} aria-invalid={Boolean(errors.email)} />{errors.email && <small>{errors.email}</small>}</Field>
        <Field><span>Primary phone</span><input type="tel" value={facts.primary_phone || ''} maxLength={30} onChange={(event) => update('primary_phone', event.target.value || null)} aria-invalid={Boolean(errors.primary_phone)} />{errors.primary_phone && <small>{errors.primary_phone}</small>}</Field>
      </Grid>
      {error && <Warning $error role="alert" style={{ marginTop: 13 }}><ExclamationTriangleIcon /> {error}</Warning>}
    </form>
  </AccessibleDialog>;
}

function EvidenceDialog({ workspace, busy, error, onClose, onSubmit }: { workspace: FamilyAuthorityWorkspaceRecord; busy: boolean; error: string; onClose: () => void; onSubmit: (input: { evidenceKind: AuthorityEvidenceKind; sourceLabel: string; issuedAt: string | null; capturedAt: string | null; expiresAt: string | null; object: AuthorityEvidenceObject | null; file: File | null }) => void }) {
  const [kind, setKind] = useState<AuthorityEvidenceKind>('identity_document');
  const [sourceLabel, setSourceLabel] = useState('');
  const [issuedAt, setIssuedAt] = useState(''); const [capturedAt, setCapturedAt] = useState(''); const [expiresAt, setExpiresAt] = useState('');
  const [objectId, setObjectId] = useState(''); const [file, setFile] = useState<File | null>(null); const [localError, setLocalError] = useState('');
  const documentKind = DOCUMENT_EVIDENCE_KINDS.has(kind);
  const objects = attachableEvidenceObjects(workspace, kind);
  const submit = (event: FormEvent) => {
    event.preventDefault(); setLocalError('');
    if (!sourceLabel.trim()) { setLocalError('Enter a short internal source label.'); return; }
    if (documentKind && !file && !objectId) { setLocalError('Choose a new document or one clean, unused document.'); return; }
    if (issuedAt && expiresAt && new Date(expiresAt) <= new Date(issuedAt)) { setLocalError('Expiry must be later than the issue time.'); return; }
    onSubmit({ evidenceKind: kind, sourceLabel: sourceLabel.trim(), issuedAt: toUtc(issuedAt), capturedAt: toUtc(capturedAt), expiresAt: toUtc(expiresAt), object: objects.find((item) => item.id === objectId) || null, file });
  };
  return <AccessibleDialog title="Record authority evidence" description="Documents are quarantined and scanned before they can be attached. Administrative review records what staff observed; it is not legal interpretation." busy={busy} onClose={onClose} footer={<><ActionButton type="button" onClick={onClose} disabled={busy}>Cancel</ActionButton><ActionButton type="submit" form="authority-evidence-form" $variant="primary" disabled={busy}>{busy ? 'Securing document…' : 'Record evidence'}</ActionButton></>}>
    <form id="authority-evidence-form" onSubmit={submit} noValidate><Grid>
      <Field><span>Evidence kind *</span><select value={kind} onChange={(event) => { setKind(event.target.value as AuthorityEvidenceKind); setObjectId(''); setFile(null); }}>{AUTHORITY_EVIDENCE_KINDS.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field>
      <Field><span>Internal source label *</span><input maxLength={160} value={sourceLabel} onChange={(event) => setSourceLabel(event.target.value)} placeholder="Received from guardian at office" /></Field>
      {documentKind && <><Field $wide><span>New document</span><input type="file" accept="application/pdf,image/jpeg,image/png" onChange={(event) => { setFile(event.target.files?.[0] || null); if (event.target.files?.[0]) setObjectId(''); }} /><FinePrint>PDF, JPEG, or PNG. A new file stays quarantined until the server scan returns clean.</FinePrint></Field>{objects.length > 0 && <Field $wide><span>Or choose a clean, unused document</span><select value={objectId} onChange={(event) => { setObjectId(event.target.value); if (event.target.value) setFile(null); }}><option value="">Choose a clean document…</option>{objects.map((item) => <option key={item.id} value={item.id}>{item.original_filename || 'Protected document'} · {Math.ceil(item.byte_size / 1024)} KiB</option>)}</select></Field>}</>}
      {!documentKind && <Warning><ShieldCheckIcon /> This evidence kind records an observed or reported fact and does not accept a document attachment.</Warning>}
      <Field><span>Issued at</span><input type="datetime-local" value={issuedAt} onChange={(event) => setIssuedAt(event.target.value)} /></Field>
      <Field><span>Captured at</span><input type="datetime-local" value={capturedAt} onChange={(event) => setCapturedAt(event.target.value)} /></Field>
      <Field><span>Expires at</span><input type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} /></Field>
    </Grid>{(localError || error) && <Warning $error role="alert" style={{ marginTop: 13 }}><ExclamationTriangleIcon /> {localError || error}</Warning>}</form>
  </AccessibleDialog>;
}

function EvidenceActionDialog({ kind, evidence, workspace, busy, error, onClose, onSubmit }: { kind: 'review' | 'reject' | 'invalidate' | 'supersede'; evidence: AuthorityEvidence; workspace: FamilyAuthorityWorkspaceRecord; busy: boolean; error: string; onClose: () => void; onSubmit: (value: string, note: string | null) => void }) {
  const choices = kind === 'review' ? reviewEpistemicOptions(evidence.evidence_kind) : kind === 'reject' ? REJECTION_REASONS : kind === 'invalidate' ? INVALIDATION_REASONS : reviewedReplacementEvidence(workspace, evidence.id).map((item) => item.id);
  const [value, setValue] = useState(String(choices[0] || ''));
  const [note, setNote] = useState(''); const [localError, setLocalError] = useState('');
  const submit = (event: FormEvent) => { event.preventDefault(); if (!value) { setLocalError('Choose a value before continuing.'); return; } if ((kind === 'reject' || kind === 'invalidate') && value === 'other' && !note.trim()) { setLocalError('Enter the confidential reason.'); return; } onSubmit(value, value === 'other' ? note.trim() : null); };
  const title = kind === 'review' ? 'Record administrative assessment' : kind === 'reject' ? 'Reject this evidence' : kind === 'invalidate' ? 'Invalidate this evidence' : 'Supersede this evidence';
  return <AccessibleDialog title={title} description={`${evidence.source_label}. This app records the bounded administrative action and never interprets a court order or decides legal authority.`} busy={busy} onClose={onClose} footer={<><ActionButton type="button" onClick={onClose} disabled={busy}>Cancel</ActionButton><ActionButton type="submit" form="authority-evidence-action" $variant={kind === 'review' ? 'primary' : 'danger'} disabled={busy}>{busy ? 'Saving…' : title}</ActionButton></>}>
    <form id="authority-evidence-action" onSubmit={submit}><Field><span>{kind === 'review' ? 'What was observed?' : kind === 'supersede' ? 'Reviewed replacement evidence' : 'Reason'}</span><select value={value} onChange={(event) => setValue(event.target.value)}>{choices.map((choice) => <option key={choice} value={choice}>{kind === 'supersede' ? workspace.evidence.find((item) => item.id === choice)?.source_label || choice : authorityLabel(choice)}</option>)}</select></Field>{(kind === 'reject' || kind === 'invalidate') && value === 'other' && <Field style={{ marginTop: 12 }}><span>Confidential note *</span><textarea maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} /></Field>}{kind === 'supersede' && choices.length === 0 && <Warning><ExclamationTriangleIcon /> Record and review replacement evidence before superseding this item.</Warning>}{(localError || error) && <Warning $error role="alert" style={{ marginTop: 12 }}><ExclamationTriangleIcon /> {localError || error}</Warning>}</form>
  </AccessibleDialog>;
}

export default function FamilyAuthorityWorkspace({ family, organizationId }: { family: FamilyDetailRecord; organizationId: string }) {
  const recovery = useChildcareCommandRecovery();
  const session = useSession();
  const location = useLocation(); const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>('loading'); const [workspace, setWorkspace] = useState<FamilyAuthorityWorkspaceRecord | null>(null);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false); const [dialog, setDialog] = useState<DialogState>(null); const [tab, setTab] = useState<AuthorityWorkspaceTab>('people');
  const errorRef = useRef<HTMLDivElement>(null);
  const requestGeneration = useRef(0);
  const routeFocus = useMemo(() => parseAuthorityDeepLink(location.search), [location.search]);
  const deepLink = routeFocus.focus;
  const actorUserId = session.user?.id || '';

  const load = useCallback(async (signal?: AbortSignal, preserveActionError = false): Promise<FamilyAuthorityWorkspaceRecord | null> => {
    const generation = ++requestGeneration.current;
    const isCurrent = () => requestGeneration.current === generation && !signal?.aborted;
    try {
      const next = await fetchFamilyAuthorityWorkspace(family.id, organizationId, signal);
      if (!isCurrent()) return null;
      setWorkspace(next); setPhase('ready'); if (!preserveActionError) setError('');
      return next;
    } catch (caught) {
      if (!isCurrent() || (caught instanceof DOMException && caught.name === 'AbortError')) return null;
      setWorkspace(null);
      if (isFamilyAuthorityUnavailable(caught)) { setPhase('unavailable'); setError(errorMessage(caught)); }
      else { setPhase('error'); setError(errorMessage(caught)); }
      return null;
    }
  }, [family.id, organizationId]);

  useEffect(() => {
    const controller = new AbortController();
    setPhase('loading');
    void load(controller.signal);
    return () => {
      controller.abort();
      requestGeneration.current += 1;
    };
  }, [load]);
  useRealtimeRefresh({ scope: 'family-authority', organizationId, enabled: phase !== 'unavailable', entityTypes: ['authority_person', 'authority_evidence', 'authority_evidence_object', 'release_authorization', 'release_rule', 'consent', 'child_authority_head'], refresh: async () => { await load(); } });
  useEffect(() => {
    if (!workspace || !deepLink) return;
    setTab(authorityWorkspaceTabForFocus(deepLink));
    if (isAuthorityDecisionFocus(deepLink)) return;
    requestAnimationFrame(() => { const target = document.getElementById(`authority-${deepLink.kind}-${deepLink.id}`); target?.scrollIntoView({ behavior: 'smooth', block: 'center' }); target?.focus({ preventScroll: true }); });
  }, [deepLink, workspace]);

  const selectTab = (nextTab: AuthorityWorkspaceTab) => {
    setTab(nextTab);
    if (!shouldClearAuthorityFocusForTabSelection(deepLink, nextTab)) return;
    navigate(
      { pathname: location.pathname, search: '', hash: location.hash },
      { replace: true, state: location.state },
    );
  };

  const mutationLocked = childcareMutationControlDisabled(recovery.laneBlocked, busy, !actorUserId);
  const run = async <Result extends { receipt: { actionRoute: string } }>(metadata: ChildcareMutationMetadata, send: (operationId: string) => Promise<Result>, success: string): Promise<Result | null> => {
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await recovery.execute(metadata, send);
      await load(); setNotice(success); setDialog(null); navigate(result.receipt.actionRoute, { replace: true }); return result;
    } catch (caught) {
      if (caught instanceof ChildcareCommandRecoveredCommitError) { await load(); setNotice('CareSync confirmed the interrupted authority change was saved.'); setDialog(null); navigate(caught.resolution.actionRoute, { replace: true }); return null; }
      setError(errorMessage(caught)); requestAnimationFrame(() => errorRef.current?.focus()); return null;
    } finally { setBusy(false); }
  };

  const personSubmit = async (sourceKey: string, facts: AuthorityPersonFacts) => {
    if (!workspace || dialog?.kind !== 'person') return;
    const operation = createClientOperationId(); const existing = dialog.person;
    const source = authorityPersonSourceOptions(family, workspace.people).find((option) => option.key === sourceKey)?.source || { kind: 'manual' as const };
    await run({ clientOperationId: operation, commandType: existing ? 'family.authority.person.replace' : 'family.authority.person.create', targetType: 'authority_person', expectedTargetId: existing?.id || null, expectedActionOwnerId: family.id }, (id) => existing ? replaceAuthorityPerson(family.id, existing.id, existing.version, facts, organizationId, id) : createAuthorityPerson(family.id, { source, facts }, organizationId, id), existing ? 'Authority-person facts were replaced with a new immutable version.' : 'Authority person was added. No pickup authorization was implied.');
  };

  const retire = async (person: AuthorityPerson) => { const operation = createClientOperationId(); await run({ clientOperationId: operation, commandType: 'family.authority.person.retire', targetType: 'authority_person', expectedTargetId: person.id, expectedActionOwnerId: family.id }, (id) => retireAuthorityPerson(family.id, person.id, person.version, organizationId, id), 'The authority person was retired; historical facts remain intact.'); };

  const scanObject = async (object: AuthorityEvidenceObject, automatic = false): Promise<AuthorityEvidenceObject | null> => {
    const operation = createClientOperationId();
    const result = await run({ clientOperationId: operation, commandType: 'family.authority.evidence_object.scan', targetType: 'authority_evidence_object', expectedTargetId: object.id, expectedActionOwnerId: family.id }, (id) => scanAuthorityEvidenceObject(family.id, object.id, 1, organizationId, id), automatic ? 'The document passed quarantine scanning.' : 'The document scan was completed.');
    if (result?.resource) return result.resource;
    const canonical = await load(undefined, true);
    return canonical?.evidence_objects.find((item) => item.id === object.id) || null;
  };

  const evidenceSubmit = async (input: { evidenceKind: AuthorityEvidenceKind; sourceLabel: string; issuedAt: string | null; capturedAt: string | null; expiresAt: string | null; object: AuthorityEvidenceObject | null; file: File | null }) => {
    let object = input.object;
    if (input.file) {
      const uploadOperation = createClientOperationId();
      const uploaded = await run({ clientOperationId: uploadOperation, commandType: 'family.authority.evidence_object.upload', targetType: 'authority_evidence_object', expectedTargetId: null, expectedActionOwnerId: family.id }, (id) => uploadAuthorityEvidenceObject(family.id, input.evidenceKind, input.file!, organizationId, id), 'The document is quarantined and awaiting its required server scan.');
      if (!uploaded) return;
      object = await scanObject(uploaded.resource, true);
      if (!object?.valid_for_evidence) {
        setDialog(null); setTab('documents');
        setNotice(object?.lifecycle_status === 'rejected'
          ? 'The server rejected this document during its safety scan. No evidence record was created.'
          : object?.lifecycle_status === 'quarantined'
            ? 'The scanner did not complete. The canonical document is still quarantined; use Retry scan when the scanner is available. No evidence record was created.'
            : 'CareSync could not confirm the canonical scan state. No evidence record was created; check the saved-result notice before retrying.');
        return;
      }
    }
    if (DOCUMENT_EVIDENCE_KINDS.has(input.evidenceKind) && !object?.valid_for_evidence) { setError('A clean, unused document is required for this evidence kind.'); return; }
    const operation = createClientOperationId();
    await run({ clientOperationId: operation, commandType: 'family.authority.evidence.record', targetType: 'authority_evidence', expectedTargetId: null, expectedActionOwnerId: family.id }, (id) => recordAuthorityEvidence(family.id, { evidence_kind: input.evidenceKind, source_label: input.sourceLabel, ...(object ? { evidence_object_id: object.id } : {}), issued_at: input.issuedAt, captured_at: input.capturedAt, expires_at: input.expiresAt }, organizationId, id), 'Authority evidence was recorded as unreviewed. It does not yet authorize release or consent.');
  };

  const evidenceAction = async (kind: 'review' | 'reject' | 'invalidate' | 'supersede', evidence: AuthorityEvidence, value: string, note: string | null) => {
    if (kind === 'review' && workspace && !evidenceReviewAssignment(workspace, evidence, actorUserId).canCurrentActorReview) {
      setDialog(null);
      setError('You recorded or uploaded this evidence. Another active owner or administrator must review it.');
      requestAnimationFrame(() => errorRef.current?.focus());
      return;
    }
    const operation = createClientOperationId(); const command = `family.authority.evidence.${kind}` as ChildcareMutationMetadata['commandType'];
    await run({ clientOperationId: operation, commandType: command, targetType: 'authority_evidence', expectedTargetId: evidence.id, expectedActionOwnerId: family.id }, (id) => kind === 'review' ? reviewAuthorityEvidence(family.id, evidence.id, evidence.version, value as AuthorityEvidenceEpistemicStatus, organizationId, id) : kind === 'reject' ? rejectAuthorityEvidence(family.id, evidence.id, evidence.version, value as AuthorityEvidenceRejectionReason, note, organizationId, id) : kind === 'invalidate' ? invalidateAuthorityEvidence(family.id, evidence.id, evidence.version, value as AuthorityEvidenceInvalidationReason, note, organizationId, id) : supersedeAuthorityEvidence(family.id, evidence.id, evidence.version, value, organizationId, id), kind === 'review' ? 'The administrative assessment was recorded. Release and consent remain unenforced.' : `The evidence was ${kind === 'reject' ? 'rejected' : kind === 'invalidate' ? 'invalidated' : 'superseded'}.`);
  };

  const downloadObject = async (object: AuthorityEvidenceObject) => {
    setBusy(true); setError('');
    try { const blob = await fetchAuthorityEvidenceObjectContent(family.id, object.id, organizationId); const href = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = href; anchor.download = `evidence-${object.id}`; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(href), 0); }
    catch (caught) { setError(errorMessage(caught)); }
    finally { setBusy(false); }
  };

  if (phase !== 'ready' || !workspace) return <Panel $accent="cyan"><Header><div><Eyebrow><ShieldCheckIcon width={14} /> Authority & consent</Eyebrow><h2>Family authority workspace</h2><p>Confidential, owner/administrator-only authority records load independently from the family profile.</p></div></Header><State>{phase === 'loading' ? <div><ArrowPathIcon /><h3>Loading authority records</h3><p>CareSync is reading the canonical family-authority workspace.</p></div> : phase === 'unavailable' ? <div><ShieldCheckIcon /><h3>Authority kernel not enabled</h3><p>{error} The family profile remains available and no legacy pickup marker is promoted.</p></div> : <div><ExclamationTriangleIcon /><h3>Authority records stayed closed</h3><p>{error}</p><ActionButton type="button" onClick={() => void load()}><ArrowPathIcon /> Try again</ActionButton></div>}</State></Panel>;

  const counts = authorityWorkspaceCounts(workspace, actorUserId);
  const targetMissing = Boolean(deepLink && !authorityWorkspaceFocusExists(workspace, deepLink));
  const decisionFocus = isAuthorityDecisionFocus(deepLink) ? deepLink : null;
  return <Panel $accent="cyan" aria-labelledby="family-authority-title">
    <Header><div><Eyebrow><ShieldCheckIcon width={14} /> Confidential authority administration</Eyebrow><h2 id="family-authority-title">Authority & consent</h2><p>Stable people, quarantined documents, evidence assessments, and per-child authority history. Existing pickup/consent booleans remain legacy profile markers.</p></div><ActionButton type="button" onClick={() => void load()} disabled={busy}><ArrowPathIcon /> Refresh</ActionButton></Header>
    <Warning><ExclamationTriangleIcon /><span><strong>Educator checkout enforcement is not active.</strong> Administrators can record reviewed release and consent decisions here, but those records do not yet create an educator release context or interpret legal documents.</span></Warning>
    {notice && <Success role="status" aria-live="polite"><CheckCircleIcon /> {notice}</Success>}
    {error && <Warning ref={errorRef} tabIndex={-1} $error role="alert"><ExclamationTriangleIcon /> {error}</Warning>}
    {routeFocus.message && <Warning role="alert"><ExclamationTriangleIcon /> {routeFocus.message}</Warning>}
    {targetMissing && <Warning role="status"><ExclamationTriangleIcon /> The exact authority target is not present in this family workspace. CareSync did not select another record.</Warning>}
    <Metrics aria-label="Authority workspace summary"><Metric><span>Active people</span><strong>{counts.activePeople}</strong></Metric><Metric><span>Ready for your review</span><strong>{counts.awaitingYourReview}</strong></Metric><Metric><span>Recorded by you</span><strong>{counts.recordedByYouAwaitingReview}</strong></Metric><Metric><span>Unreviewed evidence</span><strong>{counts.unreviewedEvidence}</strong></Metric><Metric><span>Currently reviewed evidence</span><strong>{counts.validEvidence}</strong></Metric><Metric><span>Children with authority history</span><strong>{counts.authorityHistoryChildren}/{workspace.children.length}</strong></Metric></Metrics>
    <Tabs role="tablist" aria-label="Authority workspace sections"><Tab type="button" role="tab" aria-selected={tab === 'people'} $active={tab === 'people'} onClick={() => selectTab('people')}>People</Tab><Tab type="button" role="tab" aria-selected={tab === 'evidence'} $active={tab === 'evidence'} onClick={() => selectTab('evidence')}>Evidence</Tab><Tab type="button" role="tab" aria-selected={tab === 'documents'} $active={tab === 'documents'} onClick={() => selectTab('documents')}>Quarantine</Tab><Tab type="button" role="tab" aria-selected={tab === 'decisions'} $active={tab === 'decisions'} onClick={() => selectTab('decisions')}>Release & consent</Tab></Tabs>
    {tab === 'people' && <Section role="tabpanel"><SectionHead><div><h3>Authority people</h3><p>Identity versions only. A person is not a release grant.</p></div><ActionButton type="button" $variant="primary" disabled={mutationLocked} onClick={() => { setError(''); setDialog({ kind: 'person', person: null }); }}><PlusIcon /> Add person</ActionButton></SectionHead><Cards>{workspace.people.length ? workspace.people.map((person) => { const facts = person.current_version?.facts; const focused = deepLink?.kind === 'person' && deepLink.id === person.id; return <Card id={`authority-person-${person.id}`} key={person.id} tabIndex={-1} $focused={focused}><CardTop><div><strong>{facts ? `${facts.first_name} ${facts.last_name}` : 'Retired authority person'}</strong><small>{facts ? `${authorityLabel(facts.relationship_kind)} · version ${person.version}` : `Retired ${dateTimeLabel(person.retired_at)} · version ${person.version}`}</small></div><StatusChip $tone={person.status === 'active' ? 'success' : 'neutral'}>{authorityLabel(person.status)}</StatusChip></CardTop>{person.status === 'active' && <CardActions><ActionButton type="button" disabled={mutationLocked} onClick={() => { setError(''); setDialog({ kind: 'person', person }); }}><PencilSquareIcon /> Replace facts</ActionButton><ActionButton type="button" $variant="danger" disabled={mutationLocked} onClick={() => { setError(''); setDialog({ kind: 'retire', person }); }}><TrashIcon /> Retire</ActionButton></CardActions>}</Card>; }) : <Empty>No authority people have been recorded. Legacy guardians and contacts have not been promoted.</Empty>}</Cards></Section>}
    {tab === 'evidence' && <Section role="tabpanel"><SectionHead><div><h3>Authority evidence</h3><p>Immutable intake and bounded administrative assessment history. A different active owner or administrator must assess each submission.</p></div><ActionButton type="button" $variant="primary" disabled={mutationLocked} onClick={() => { setError(''); setDialog({ kind: 'evidence', evidence: null }); }}><PlusIcon /> Record evidence</ActionButton></SectionHead><Cards>{workspace.evidence.length ? workspace.evidence.map((evidence) => {
      const focused = deepLink?.kind === 'evidence' && deepLink.id === evidence.id;
      const assignment = evidenceReviewAssignment(workspace, evidence, actorUserId);
      const actions = evidenceActions(evidence, assignment);
      const pendingReview = evidence.lifecycle_status === 'unreviewed' && evidence.effective_status === 'unreviewed';
      return <Card id={`authority-evidence-${evidence.id}`} key={evidence.id} tabIndex={-1} $focused={focused}><CardTop><div><strong>{evidence.source_label}</strong><small>{authorityLabel(evidence.evidence_kind)} · version {evidence.version} · {evidence.expires_at ? `expires ${dateTimeLabel(evidence.expires_at)}` : 'no expiry recorded'}</small></div><StatusChip $tone={evidence.valid_now ? 'success' : evidence.lifecycle_status === 'unreviewed' ? 'warning' : 'neutral'}>{authorityLabel(evidence.effective_status)}</StatusChip></CardTop>{pendingReview && assignment.requiresIndependentReviewer && <FinePrint><strong>{assignment.recordedByCurrentActor ? 'Recorded by you.' : 'Document uploaded by you.'}</strong> Another active owner or administrator must review this evidence. You may still reject an incorrect submission.</FinePrint>}{pendingReview && assignment.canCurrentActorReview && <FinePrint>This evidence was recorded by another user and is ready for your independent review.</FinePrint>}{actions.length > 0 && <CardActions>{actions.map((action) => <ActionButton key={action} type="button" $variant={action === 'review' ? 'primary' : action === 'reject' || action === 'invalidate' ? 'danger' : undefined} disabled={mutationLocked} onClick={() => { setError(''); setDialog({ kind: action, evidence } as DialogState); }}>{action === 'review' ? <DocumentCheckIcon /> : <ShieldCheckIcon />}{authorityLabel(action)}</ActionButton>)}</CardActions>}</Card>;
    }) : <Empty>No versioned authority evidence has been recorded. Legacy consent booleans are not evidence.</Empty>}</Cards></Section>}
    {tab === 'documents' && <Section role="tabpanel"><SectionHead><div><h3>Document quarantine</h3><p>Objects remain separate from evidence until a clean scan and single-use attachment.</p></div></SectionHead><Cards>{workspace.evidence_objects.length ? workspace.evidence_objects.map((object) => { const focused = deepLink?.kind === 'object' && deepLink.id === object.id; return <Card id={`authority-object-${object.id}`} key={object.id} tabIndex={-1} $focused={focused}><CardTop><div><strong>{object.original_filename || 'Protected document'}</strong><small>{authorityLabel(object.evidence_kind)} · {Math.ceil(object.byte_size / 1024)} KiB · version {object.version}</small></div><StatusChip $tone={object.valid_for_evidence ? 'success' : object.lifecycle_status === 'quarantined' ? 'warning' : 'neutral'}>{authorityLabel(object.lifecycle_status)}</StatusChip></CardTop><CardActions>{evidenceObjectCanScan(object) && <ActionButton type="button" $variant="primary" disabled={mutationLocked} onClick={() => void scanObject(object)}><DocumentMagnifyingGlassIcon /> Retry scan</ActionButton>}{object.valid_for_evidence && <ActionButton type="button" disabled={busy} onClick={() => void downloadObject(object)}><ArrowDownTrayIcon /> Download</ActionButton>}</CardActions></Card>; }) : <Empty>No quarantined document objects exist. New document evidence begins with a protected upload and server scan.</Empty>}</Cards></Section>}
    {tab === 'decisions' && <section role="tabpanel"><FamilyAuthorityDecisionPanel family={family} organizationId={organizationId} workspace={workspace} focus={decisionFocus} parentBusy={busy} onWorkspaceChanged={async () => { await load(); }} /></section>}
    {dialog?.kind === 'person' && <PersonDialog detail={family} workspace={workspace} person={dialog.person} busy={busy} error={error} onClose={() => setDialog(null)} onSubmit={(source, facts) => void personSubmit(source, facts)} />}
    {dialog?.kind === 'retire' && <AccessibleDialog title={`Retire ${dialog.person.current_version?.facts.first_name || 'this authority person'}?`} description="Retirement is terminal. Historical versions remain and no existing history is deleted." busy={busy} onClose={() => setDialog(null)} footer={<><ActionButton type="button" onClick={() => setDialog(null)} disabled={busy}>Keep active</ActionButton><ActionButton type="button" $variant="danger" disabled={busy} onClick={() => void retire(dialog.person)}>Retire person</ActionButton></>}><Warning><ExclamationTriangleIcon /> Confirm the exact person. Later corrections require a new authority-person record.</Warning>{error && <Warning $error role="alert"><ExclamationTriangleIcon /> {error}</Warning>}</AccessibleDialog>}
    {dialog?.kind === 'evidence' && <EvidenceDialog workspace={workspace} busy={busy} error={error} onClose={() => setDialog(null)} onSubmit={(input) => void evidenceSubmit(input)} />}
    {dialog && ['review', 'reject', 'invalidate', 'supersede'].includes(dialog.kind) && <EvidenceActionDialog kind={dialog.kind as 'review' | 'reject' | 'invalidate' | 'supersede'} evidence={(dialog as { evidence: AuthorityEvidence }).evidence} workspace={workspace} busy={busy} error={error} onClose={() => setDialog(null)} onSubmit={(value, note) => void evidenceAction(dialog.kind as 'review' | 'reject' | 'invalidate' | 'supersede', (dialog as { evidence: AuthorityEvidence }).evidence, value, note)} />}
  </Panel>;
}
