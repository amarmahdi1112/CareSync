import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  HandRaisedIcon,
  KeyIcon,
  PlusIcon,
  ShieldExclamationIcon,
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
import {
  RELEASE_AUTHORIZATION_SAVED_COPY,
  RELEASE_AUTHORITY_BOUNDARY_COPY,
} from '../../config/activeRuntimeCopy';
import { useMotion } from '../../motion';
import { fetchEnrollmentFacilities, type EnrollmentFacilityOption } from '../children/childrenApi';
import { useRealtimeRefresh } from '../../realtime/RealtimeContext';
import {
  createReleaseRule,
  FamilyAuthorityApiError,
  fetchConsentPolicies,
  grantReleaseAuthorization,
  publishConsentPolicy,
  recordChildConsent,
  revokeReleaseAuthorization,
  revokeReleaseRule,
  withdrawChildConsent,
} from './familyAuthorityApi';
import {
  activeAuthorityPeople,
  authorityLabel,
  authorityWorkspaceFocusExists,
  CONSENT_PURPOSES,
  CONSENT_SIGNER_REQUIREMENTS,
  CONSENT_WITHDRAWAL_REASONS,
  currentConsentPolicies,
  effectiveRecordState,
  explicitlySelectedCurrentPerson,
  personCanUseBasis,
  RELEASE_AUTHORITY_BASES,
  RELEASE_REVOCATION_REASONS,
  RELEASE_RULE_KINDS,
  RELEASE_VERIFICATION_POLICIES,
  releaseRuleRequiresDirectingPerson,
  RESTRICTION_AUTHORITY_BASES,
  reviewedEvidenceForBasis,
  signedConsentEvidence,
  type AuthorityDecisionFocus,
} from './familyAuthorityModel';
import type { FamilyDetailRecord } from './types';
import type {
  AuthorityEvidence,
  AuthorityPerson,
  ChildAuthoritySummary,
  ChildConsentDecision,
  ConsentDecision,
  ConsentPolicyVersion,
  ConsentScope,
  FamilyAuthorityWorkspaceRecord,
  ReleaseAuthorization,
  ReleaseRule,
  ReviewedAuthorityBasis,
} from './familyAuthorityTypes';

const Shell = styled.div`display: grid; gap: 15px;`;
const Notice = styled.div<{ $error?: boolean; $success?: boolean }>`
  display: flex; align-items: flex-start; gap: 9px; padding: 12px 13px;
  border: 1px solid ${({ $error, $success, theme }) => $error ? theme.color.coral : $success ? theme.color.mint : theme.color.amber};
  border-radius: 12px 5px 12px 5px; color: ${({ theme }) => theme.color.textSoft};
  background: ${({ $error, $success, theme }) => `color-mix(in srgb, ${$error ? theme.color.coral : $success ? theme.color.mint : theme.color.amber} 8%, ${theme.color.surfaceStrong})`};
  font-size: .72rem; line-height: 1.55; outline: 0;
  svg { width: 18px; flex: 0 0 auto; color: ${({ $error, $success, theme }) => $error ? theme.color.coral : $success ? theme.color.mint : theme.color.amber}; }
`;
const Block = styled(GlassPanel)<{ $tone?: 'positive' | 'restriction' | 'consent' }>`
  display: grid; gap: 12px; padding: 16px;
  border-color: ${({ $tone, theme }) => $tone === 'positive' ? `color-mix(in srgb, ${theme.color.mint} 45%, ${theme.color.border})` : $tone === 'restriction' ? `color-mix(in srgb, ${theme.color.coral} 40%, ${theme.color.border})` : `color-mix(in srgb, ${theme.color.cyan} 42%, ${theme.color.border})`};
`;
const Head = styled.header`
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  h3 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: .94rem; font-weight: 550; }
  p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.55; }
  @media (max-width: 600px) { flex-direction: column; }
`;
const ChildGrid = styled.div`display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr)); gap: 10px;`;
const ChildCard = styled.article`display: grid; align-content: start; gap: 11px; min-width: 0; padding: 13px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 13px 6px 13px 6px; background: ${({ theme }) => theme.color.surfaceStrong};`;
const CardHead = styled.div`display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; strong { font-size: .79rem; font-weight: 620; } small { display: block; margin-top: 3px; color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; }`;
const Rows = styled.div`display: grid; gap: 7px;`;
const Row = styled.div<{ $focused?: boolean }>`
  display: grid; gap: 5px; padding: 9px; border: 1px solid ${({ $focused, theme }) => $focused ? theme.color.cyan : theme.color.controlBorder}; border-radius: 9px; outline: 0; background: ${({ $focused, theme }) => $focused ? `color-mix(in srgb, ${theme.color.cyan} 9%, ${theme.color.control})` : theme.color.control}; box-shadow: ${({ $focused, theme }) => $focused ? theme.shadow.cyan : 'none'};
  header { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
  strong { font-size: .71rem; font-weight: 620; } small { color: ${({ theme }) => theme.color.textMuted}; font-size: .64rem; line-height: 1.5; overflow-wrap: anywhere; }
  &:focus-visible { outline: 2px solid ${({ theme }) => theme.color.cyan}; outline-offset: 3px; }
`;
const Actions = styled.div`display: flex; flex-wrap: wrap; gap: 7px;`;
const Empty = styled.div`padding: 12px; border: 1px dashed ${({ theme }) => theme.color.controlBorder}; border-radius: 10px; color: ${({ theme }) => theme.color.textMuted}; font-size: .69rem; line-height: 1.55; text-align: center;`;
const Backdrop = styled.div`position: fixed; z-index: 1550; inset: 0; display: grid; place-items: center; padding: 18px; background: ${({ theme }) => theme.color.overlay}; backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});`;
const Dialog = styled(GlassPanel)`display: grid; width: min(760px, 100%); max-height: calc(100dvh - 36px); grid-template-rows: auto minmax(0, 1fr) auto; overflow: hidden; outline: 0;`;
const DialogHead = styled.header`display: flex; justify-content: space-between; gap: 12px; padding: 18px; border-bottom: 1px solid ${({ theme }) => theme.color.divider}; h2 { margin: 6px 0 4px; font-family: 'CareSync Display', sans-serif; font-size: 1.12rem; font-weight: 550; } p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.55; }`;
const Body = styled.div`display: grid; align-content: start; gap: 12px; overflow-y: auto; padding: 18px;`;
const Footer = styled.footer`display: flex; justify-content: flex-end; gap: 8px; padding: 13px 18px; border-top: 1px solid ${({ theme }) => theme.color.divider};`;
const Grid = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; @media (max-width: 600px) { grid-template-columns: 1fr; }`;
const Field = styled.label<{ $wide?: boolean }>`
  display: grid; gap: 6px; min-width: 0; ${({ $wide }) => $wide ? 'grid-column: 1 / -1;' : ''}
  > span { color: ${({ theme }) => theme.color.textSoft}; font-size: .68rem; font-weight: 600; }
  input, select, textarea { width: 100%; min-height: 43px; padding: 0 10px; border: 1px solid ${({ theme }) => theme.color.controlBorder}; border-radius: 9px; outline: 0; color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.control}; font: inherit; font-size: .75rem; }
  textarea { min-height: 84px; padding-top: 9px; resize: vertical; }
  input:focus, select:focus, textarea:focus { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 14%, transparent); }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .64rem; line-height: 1.5; }
`;
const Confirm = styled.label`display: flex; gap: 9px; align-items: flex-start; color: ${({ theme }) => theme.color.textSoft}; font-size: .71rem; line-height: 1.5; input { margin-top: 3px; }`;
const PolicyText = styled.pre`
  max-height: 210px; margin: 0; overflow: auto; padding: 10px; border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 9px; color: ${({ theme }) => theme.color.textSoft}; background: ${({ theme }) => theme.color.control};
  white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: .68rem; line-height: 1.6;
`;
const PolicyDetails = styled.details`
  color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem;
  summary { cursor: pointer; color: ${({ theme }) => theme.color.textSoft}; font-weight: 600; }
  ${PolicyText} { margin-top: 8px; }
`;

type MutationResult = { receipt: { actionRoute: string } };
type DecisionDialog =
  | { kind: 'grant'; child: ChildAuthoritySummary }
  | { kind: 'rule'; child: ChildAuthoritySummary }
  | { kind: 'consent'; child: ChildAuthoritySummary }
  | { kind: 'policy' }
  | { kind: 'revoke_authorization'; child: ChildAuthoritySummary; record: ReleaseAuthorization }
  | { kind: 'revoke_rule'; child: ChildAuthoritySummary; record: ReleaseRule }
  | { kind: 'withdraw_consent'; child: ChildAuthoritySummary; record: ChildConsentDecision };

function dateTimeLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Invalid date' : date.toLocaleString('en-CA', { dateStyle: 'medium', timeStyle: 'short' });
}

function toLocalInput(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function toUtc(value: string): string | null {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function personName(person: AuthorityPerson | undefined): string {
  const facts = person?.current_version?.facts;
  return facts ? `${facts.first_name} ${facts.last_name}` : 'Retired authority person';
}

function evidenceLabel(evidence: AuthorityEvidence): string {
  return `${evidence.source_label} · ${authorityLabel(evidence.evidence_kind)}`;
}

function statusTone(state: ReturnType<typeof effectiveRecordState>): 'success' | 'warning' | 'neutral' {
  if (state === 'current') return 'success';
  if (state === 'scheduled' || state === 'supporting_evidence_unavailable') return 'warning';
  return 'neutral';
}

function errorMessage(caught: unknown): string {
  let current = caught;
  for (let depth = 0; depth < 5; depth += 1) {
    if (current instanceof FamilyAuthorityApiError) return current.message;
    if (!current || typeof current !== 'object' || !('cause' in current)) break;
    current = (current as { cause?: unknown }).cause;
  }
  return caught instanceof Error ? caught.message : 'The authority decision could not be completed.';
}

function AccessibleDecisionDialog({ title, description, busy, onClose, children, footer }: { title: string; description: string; busy: boolean; onClose: () => void; children: ReactNode; footer: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose(); return; }
      if (event.key !== 'Tab' || !ref.current) return;
      const controls = [...ref.current.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')];
      if (!controls.length) return;
      const first = controls[0]; const last = controls.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', handler);
    requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus());
    return () => { document.body.style.overflow = oldOverflow; window.removeEventListener('keydown', handler); previous?.focus(); };
  }, [busy, onClose]);
  return createPortal(<Backdrop onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}><Dialog ref={ref} role="dialog" aria-modal="true" aria-labelledby="authority-decision-title" aria-describedby="authority-decision-description" $accent="cyan"><DialogHead><div><Eyebrow><KeyIcon width={14} /> Reviewed authority decision</Eyebrow><h2 id="authority-decision-title">{title}</h2><p id="authority-decision-description">{description}</p></div><IconButton type="button" onClick={onClose} disabled={busy} aria-label="Close decision dialog"><XMarkIcon /></IconButton></DialogHead><Body>{children}</Body><Footer>{footer}</Footer></Dialog></Backdrop>, document.body);
}

interface EditorSubmit {
  (input: Record<string, unknown>): void;
}

function DecisionEditor({ dialog, family, workspace, policies, facilities, actorUserId, busy, error, onClose, onSubmit }: { dialog: DecisionDialog; family: FamilyDetailRecord; workspace: FamilyAuthorityWorkspaceRecord; policies: ConsentPolicyVersion[]; facilities: EnrollmentFacilityOption[]; actorUserId: string; busy: boolean; error: string; onClose: () => void; onSubmit: EditorSubmit }) {
  const people = useMemo(() => activeAuthorityPeople(workspace), [workspace]);
  const now = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(() => toLocalInput(now));
  const [until, setUntil] = useState(() => toLocalInput(new Date(now.getTime() + 30 * 86_400_000)));
  const [basis, setBasis] = useState<ReviewedAuthorityBasis>('guardian_record');
  const [personId, setPersonId] = useState(''); const [recipientId, setRecipientId] = useState('');
  const [evidenceId, setEvidenceId] = useState(''); const [decisionEvidenceId, setDecisionEvidenceId] = useState('');
  const [verification, setVerification] = useState<(typeof RELEASE_VERIFICATION_POLICIES)[number]>('government_photo_id_or_documented_familiarity');
  const [ruleKind, setRuleKind] = useState<(typeof RELEASE_RULE_KINDS)[number]>('deny'); const [scopeKind, setScopeKind] = useState<'all_recipients' | 'specific_person'>('all_recipients'); const [scopePersonId, setScopePersonId] = useState(''); const [directingPersonId, setDirectingPersonId] = useState(''); const [confidentialReason, setConfidentialReason] = useState('');
  const [purpose, setPurpose] = useState<(typeof CONSENT_PURPOSES)[number]>('off_site_activity'); const [policyVersion, setPolicyVersion] = useState(1); const [title, setTitle] = useState(''); const [contentText, setContentText] = useState(''); const [signerRequirement, setSignerRequirement] = useState<(typeof CONSENT_SIGNER_REQUIREMENTS)[number]>('guardian_record');
  const currentPolicies = useMemo(() => currentConsentPolicies(policies).filter((policy) => policy.signer_authority_requirement !== 'specific_reviewed_authority'), [policies]);
  const [selectedPolicyId, setSelectedPolicyId] = useState(() => currentPolicies[0]?.id || ''); const [consentDecision, setConsentDecision] = useState<ConsentDecision>('granted'); const [consentScopeKind, setConsentScopeKind] = useState<ConsentScope['kind']>('policy'); const [facilityId, setFacilityId] = useState(''); const [activityReference, setActivityReference] = useState('');
  const [reason, setReason] = useState<string>(RELEASE_REVOCATION_REASONS[0]); const [confirmed, setConfirmed] = useState(false); const [localError, setLocalError] = useState('');
  const selectedPolicy = currentPolicies.find((policy) => policy.id === selectedPolicyId);
  const effectiveBasis: ReviewedAuthorityBasis = dialog.kind === 'consent'
    ? selectedPolicy?.signer_authority_requirement === 'legal_decision_maker' ? 'reviewed_custody_evidence' : 'guardian_record'
    : basis;
  const eligiblePeople = people.filter((person) => personCanUseBasis(person, effectiveBasis));
  const selectedPerson = explicitlySelectedCurrentPerson(workspace.people, personId, effectiveBasis);
  const selectedDirector = explicitlySelectedCurrentPerson(workspace.people, directingPersonId, effectiveBasis);
  const authorityEvidence = reviewedEvidenceForBasis(workspace, effectiveBasis, actorUserId);
  const selectedEvidence = authorityEvidence.find((item) => item.id === evidenceId);
  const consentEvidence = signedConsentEvidence(workspace, actorUserId);
  const selectedDecisionEvidence = consentEvidence.find((item) => item.id === decisionEvidenceId);
  const child = 'child' in dialog ? family.children.find((item) => item.id === dialog.child.child_id) : null;
  const childLabel = child ? `${child.first_name} ${child.last_name}` : 'this child';
  const destructive = dialog.kind === 'revoke_authorization' || dialog.kind === 'revoke_rule' || dialog.kind === 'withdraw_consent';

  useEffect(() => {
    if (dialog.kind === 'policy') {
      const versions = policies.filter((policy) => policy.purpose_code === purpose).map((policy) => policy.version_number);
      setPolicyVersion(Math.max(0, ...versions) + 1);
    }
  }, [dialog.kind, policies, purpose]);

  useEffect(() => {
    if (dialog.kind !== 'consent' || !selectedPolicy) return;
    const start = new Date(Math.max(Date.now(), Date.parse(selectedPolicy.effective_from)));
    const end = new Date(Math.min(start.getTime() + 30 * 86_400_000, Date.parse(selectedPolicy.effective_until)));
    setFrom(toLocalInput(start)); setUntil(toLocalInput(end)); setPersonId(''); setEvidenceId('');
  }, [dialog.kind, selectedPolicy]);

  const submit = (event: FormEvent) => {
    event.preventDefault(); setLocalError('');
    if (destructive) {
      if (!confirmed) { setLocalError('Confirm that you understand this transition is one-way.'); return; }
      onSubmit({ reason_code: reason }); return;
    }
    const effectiveFrom = toUtc(from); const effectiveUntil = toUtc(until);
    if (!effectiveFrom || !effectiveUntil || Date.parse(effectiveUntil) <= Date.parse(effectiveFrom)) { setLocalError('Choose a finite end time later than the start time.'); return; }
    if (dialog.kind === 'policy') {
      if (!title.trim() || !contentText.trim() || contentText.trim().length > 20_000) { setLocalError('Enter a title and policy content of 20,000 characters or fewer.'); return; }
      onSubmit({ purpose_code: purpose, version_number: policyVersion, title: title.trim(), content_text: contentText.trim(), signer_authority_requirement: signerRequirement, effective_from: effectiveFrom, effective_until: effectiveUntil }); return;
    }
    if (dialog.kind === 'grant') {
      const recipient = explicitlySelectedCurrentPerson(workspace.people, recipientId);
      if (!recipient?.current_version) { setLocalError('Choose the exact active recipient before granting release authorization.'); return; }
      if (!selectedPerson?.current_version) { setLocalError('Choose the exact active grantor and current identity version.'); return; }
      if (!selectedEvidence?.current_assessment) { setLocalError('Choose exact current reviewed basis evidence assessed by a different administrator.'); return; }
      onSubmit({ recipient_person_id: recipient.id, verification_policy_code: verification, grantor: { person_id: selectedPerson.id, person_version_id: selectedPerson.current_version.id, authority_basis: effectiveBasis, basis_evidence_id: selectedEvidence.id, basis_evidence_assessment_id: selectedEvidence.current_assessment.id }, effective_from: effectiveFrom, effective_until: effectiveUntil }); return;
    }
    if (dialog.kind === 'rule') {
      const specific = explicitlySelectedCurrentPerson(workspace.people, scopePersonId);
      if (scopeKind === 'specific_person' && !specific?.current_version) { setLocalError('Choose the exact active person this restriction applies to.'); return; }
      if (!selectedEvidence?.current_assessment) { setLocalError('Choose exact current reviewed restriction-basis evidence assessed by a different administrator.'); return; }
      const directorRequired = releaseRuleRequiresDirectingPerson(effectiveBasis);
      if (directorRequired && (!selectedDirector?.current_version || selectedDirector.source.kind !== 'guardian')) { setLocalError('Guardian-record restrictions require one explicitly selected current directing guardian from a saved guardian source.'); return; }
      if (!directorRequired && directingPersonId && !selectedDirector?.current_version) { setLocalError('Choose a current directing person or leave the optional selection empty.'); return; }
      if (!confidentialReason.trim()) { setLocalError('Record a concise confidential administrative reason.'); return; }
      onSubmit({ rule_kind: ruleKind, scope: scopeKind === 'all_recipients' ? { kind: 'all_recipients' } : { kind: 'specific_person', person_id: specific!.id }, directing_person: selectedDirector?.current_version ? { person_id: selectedDirector.id, person_version_id: selectedDirector.current_version.id } : null, authority_basis_code: effectiveBasis, basis_evidence_id: selectedEvidence.id, basis_evidence_assessment_id: selectedEvidence.current_assessment.id, confidential_reason: confidentialReason.trim(), effective_from: effectiveFrom, effective_until: effectiveUntil }); return;
    }
    if (!selectedPerson?.current_version) { setLocalError('Choose the exact active consent signer and current identity version.'); return; }
    if (!selectedEvidence?.current_assessment) { setLocalError('Choose exact current reviewed signer-authority evidence assessed by a different administrator.'); return; }
    if (!selectedPolicy || !selectedDecisionEvidence?.current_assessment) { setLocalError('Choose one current policy and exact distinct reviewed signed-consent evidence.'); return; }
    if (Date.parse(effectiveFrom) < Date.parse(selectedPolicy.effective_from) || Date.parse(effectiveUntil) > Date.parse(selectedPolicy.effective_until)) { setLocalError('The consent decision window must stay inside the selected policy window.'); return; }
    if (selectedDecisionEvidence.id === selectedEvidence.id) { setLocalError('Signer authority evidence and signed-consent evidence must be distinct.'); return; }
    let scope: ConsentScope = { kind: 'policy' };
    if (consentScopeKind === 'facility') { if (!facilityId) { setLocalError('Choose an active facility.'); return; } scope = { kind: 'facility', facility_id: facilityId }; }
    if (consentScopeKind === 'named_activity') { if (!activityReference.trim()) { setLocalError('Name the exact activity.'); return; } scope = { kind: 'named_activity', reference: activityReference.trim() }; }
    onSubmit({ purpose_code: selectedPolicy.purpose_code, policy_version_id: selectedPolicy.id, signer: { person_id: selectedPerson.id, person_version_id: selectedPerson.current_version.id, authority_basis: effectiveBasis, authority_evidence_id: selectedEvidence.id, authority_evidence_assessment_id: selectedEvidence.current_assessment.id }, evidence_id: selectedDecisionEvidence.id, evidence_assessment_id: selectedDecisionEvidence.current_assessment.id, decision: consentDecision, scope, effective_from: effectiveFrom, effective_until: effectiveUntil });
  };

  const titleText = dialog.kind === 'grant' ? `Grant release authorization for ${childLabel}` : dialog.kind === 'rule' ? `Add a release restriction for ${childLabel}` : dialog.kind === 'consent' ? `Record a consent decision for ${childLabel}` : dialog.kind === 'policy' ? 'Publish a consent policy version' : dialog.kind === 'withdraw_consent' ? 'Withdraw this consent decision?' : 'Revoke this release record?';
  const description = destructive ? 'This transition is permanent. History remains visible and correction requires a new record.' : 'Only active people, exact current versions, and currently reviewed evidence can be selected.';
  return <AccessibleDecisionDialog title={titleText} description={description} busy={busy} onClose={onClose} footer={<><ActionButton type="button" onClick={onClose} disabled={busy}>Cancel</ActionButton><ActionButton type="submit" form="authority-decision-form" $variant={destructive || dialog.kind === 'rule' || (dialog.kind === 'consent' && consentDecision === 'declined') ? 'danger' : 'primary'} disabled={busy}>{busy ? 'Saving…' : destructive ? 'Confirm one-way transition' : dialog.kind === 'policy' ? 'Publish immutable version' : 'Record decision'}</ActionButton></>}>
    <form id="authority-decision-form" onSubmit={submit} noValidate><Grid>
      {destructive ? <Field $wide><span>Reason *</span><select value={reason} onChange={(event) => setReason(event.target.value)}>{(dialog.kind === 'withdraw_consent' ? CONSENT_WITHDRAWAL_REASONS : RELEASE_REVOCATION_REASONS).map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field> : <>
        {dialog.kind === 'policy' ? <>
          <Field><span>Purpose *</span><select value={purpose} onChange={(event) => setPurpose(event.target.value as typeof purpose)}>{CONSENT_PURPOSES.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field>
          <Field><span>Immutable version *</span><input type="number" min={1} max={2147483647} value={policyVersion} onChange={(event) => setPolicyVersion(Number(event.target.value))} /></Field>
          <Field $wide><span>Policy title *</span><input maxLength={180} value={title} onChange={(event) => setTitle(event.target.value)} /></Field>
          <Field $wide><span>Policy content *</span><textarea maxLength={20000} value={contentText} onChange={(event) => setContentText(event.target.value)} /><small>CareSync derives the immutable private reference and SHA-256 digest after publication.</small></Field>
          <Field $wide><span>Signer authority requirement *</span><select value={signerRequirement} onChange={(event) => setSignerRequirement(event.target.value as typeof signerRequirement)}>{CONSENT_SIGNER_REQUIREMENTS.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select><small>Specific reviewed authority is intentionally unavailable in this activation slice.</small></Field>
        </> : <>
          {dialog.kind === 'grant' && <><Field><span>Authorized recipient *</span><select value={recipientId} onChange={(event) => setRecipientId(event.target.value)}><option value="">Choose the exact recipient…</option>{people.map((person) => <option key={person.id} value={person.id}>{personName(person)} · current v{person.version}</option>)}</select></Field><Field><span>Verification policy *</span><select value={verification} onChange={(event) => setVerification(event.target.value as typeof verification)}>{RELEASE_VERIFICATION_POLICIES.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field></>}
          {dialog.kind === 'rule' && <><Field><span>Restriction *</span><select value={ruleKind} onChange={(event) => setRuleKind(event.target.value as typeof ruleKind)}>{RELEASE_RULE_KINDS.map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field><Field><span>Scope *</span><select value={scopeKind} onChange={(event) => { setScopeKind(event.target.value as typeof scopeKind); setScopePersonId(''); }}><option value="all_recipients">All recipients</option><option value="specific_person">Specific person</option></select></Field>{scopeKind === 'specific_person' && <Field><span>Restricted person *</span><select value={scopePersonId} onChange={(event) => setScopePersonId(event.target.value)}><option value="">Choose the exact restricted person…</option>{people.map((person) => <option key={person.id} value={person.id}>{personName(person)} · current v{person.version}</option>)}</select></Field>}<Field $wide><span>Confidential administrative reason *</span><textarea maxLength={2000} value={confidentialReason} onChange={(event) => setConfidentialReason(event.target.value)} /><small>This reason remains inside the confidential owner/administrator workspace. Educator-safe wording is derived by the server.</small></Field></>}
          {dialog.kind === 'consent' ? <>
            <Field $wide><span>Current policy version *</span><select value={selectedPolicyId} onChange={(event) => setSelectedPolicyId(event.target.value)}><option value="">Choose a current policy…</option>{currentPolicies.map((policy) => <option key={policy.id} value={policy.id}>{policy.title} · v{policy.version_number}</option>)}</select></Field>
            {selectedPolicy && <Field $wide><span>Exact immutable policy content</span><PolicyText aria-label={`${selectedPolicy.title} policy content`}>{selectedPolicy.content_text}</PolicyText><small>Decision scope and time must stay within this exact policy version and window.</small></Field>}
            <Field><span>Decision *</span><select value={consentDecision} onChange={(event) => setConsentDecision(event.target.value as ConsentDecision)}><option value="granted">Granted</option><option value="declined">Declined</option></select></Field>
            <Field><span>Scope *</span><select value={consentScopeKind} onChange={(event) => setConsentScopeKind(event.target.value as ConsentScope['kind'])}><option value="policy">Whole policy</option><option value="facility">Specific facility</option><option value="named_activity">Named activity</option></select></Field>
            {consentScopeKind === 'facility' && <Field $wide><span>Active facility *</span><select value={facilityId} onChange={(event) => setFacilityId(event.target.value)}><option value="">Choose a facility…</option>{facilities.map((facility) => <option key={facility.id} value={facility.id}>{facility.name}</option>)}</select></Field>}
            {consentScopeKind === 'named_activity' && <Field $wide><span>Activity reference *</span><input maxLength={160} value={activityReference} onChange={(event) => setActivityReference(event.target.value)} /></Field>}
          </> : <Field><span>Reviewed authority basis *</span><select value={basis} onChange={(event) => { setBasis(event.target.value as ReviewedAuthorityBasis); setPersonId(''); setDirectingPersonId(''); setEvidenceId(''); }}>{(dialog.kind === 'rule' ? RESTRICTION_AUTHORITY_BASES : RELEASE_AUTHORITY_BASES).map((value) => <option key={value} value={value}>{authorityLabel(value)}</option>)}</select></Field>}
          {dialog.kind !== 'rule' && <Field><span>{dialog.kind === 'consent' ? 'Consent signer *' : 'Granting person *'}</span><select value={personId} onChange={(event) => setPersonId(event.target.value)}><option value="">Choose the exact eligible person…</option>{eligiblePeople.map((person) => <option key={person.id} value={person.id}>{personName(person)} · current v{person.version}{person.source.kind === 'guardian' ? ' · saved guardian source' : ''}</option>)}</select></Field>}
          {dialog.kind === 'rule' && <Field><span>{releaseRuleRequiresDirectingPerson(effectiveBasis) ? 'Directing guardian *' : 'Directing person (optional)'}</span><select value={directingPersonId} onChange={(event) => setDirectingPersonId(event.target.value)}><option value="">{releaseRuleRequiresDirectingPerson(effectiveBasis) ? 'Choose the exact directing guardian…' : 'No directing person recorded'}</option>{eligiblePeople.map((person) => <option key={person.id} value={person.id}>{personName(person)} · current v{person.version}{person.source.kind === 'guardian' ? ' · saved guardian source' : ''}</option>)}</select><small>{releaseRuleRequiresDirectingPerson(effectiveBasis) ? 'Guardian-record restrictions require a current person linked to an exact saved guardian source.' : 'Custody evidence can direct the rule without a named person; choose one only when the reviewed record identifies them.'}</small></Field>}
          <Field $wide><span>{dialog.kind === 'consent' ? 'Reviewed signer-authority evidence' : dialog.kind === 'rule' ? 'Current reviewed restriction-basis evidence' : 'Current reviewed grant basis evidence'} *</span><select value={evidenceId} onChange={(event) => setEvidenceId(event.target.value)}><option value="">Choose exact reviewed evidence…</option>{authorityEvidence.map((item) => <option key={item.id} value={item.id}>{evidenceLabel(item)}</option>)}</select><small>Evidence reviewed by the current activator is excluded to preserve maker/checker separation.</small></Field>
          {dialog.kind === 'consent' && <Field $wide><span>Distinct reviewed signed-consent evidence *</span><select value={decisionEvidenceId} onChange={(event) => setDecisionEvidenceId(event.target.value)}><option value="">Choose exact signed consent…</option>{consentEvidence.map((item) => <option key={item.id} value={item.id}>{evidenceLabel(item)}</option>)}</select></Field>}
        </>}
        <Field><span>Effective from *</span><input type="datetime-local" value={from} onChange={(event) => setFrom(event.target.value)} /></Field>
        <Field><span>Effective until *</span><input type="datetime-local" value={until} onChange={(event) => setUntil(event.target.value)} /></Field>
      </>}
    </Grid>
    {destructive && <><Notice $error style={{ marginTop: 12 }}><ExclamationTriangleIcon /> Revocation or withdrawal cannot be undone. It does not delete the historical record.</Notice><Confirm style={{ marginTop: 12 }}><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /> I reviewed the exact child and record and understand that a new record is required to correct this transition.</Confirm></>}
    {(localError || error) && <Notice $error role="alert" style={{ marginTop: 12 }}><ExclamationTriangleIcon /> {localError || error}</Notice>}
    </form>
  </AccessibleDecisionDialog>;
}

export default function FamilyAuthorityDecisionPanel({ family, organizationId, workspace, focus, parentBusy, onWorkspaceChanged }: { family: FamilyDetailRecord; organizationId: string; workspace: FamilyAuthorityWorkspaceRecord; focus: AuthorityDecisionFocus | null; parentBusy: boolean; onWorkspaceChanged: () => Promise<void> }) {
  const recovery = useChildcareCommandRecovery(); const session = useSession(); const { motionAllowed } = useMotion();
  const [policies, setPolicies] = useState<ConsentPolicyVersion[]>([]); const [facilities, setFacilities] = useState<EnrollmentFacilityOption[]>([]);
  const [loading, setLoading] = useState(true); const [supportingReady, setSupportingReady] = useState(false); const [supportError, setSupportError] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [dialog, setDialog] = useState<DecisionDialog | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const focusedRecordRef = useRef<HTMLDivElement>(null);
  const supportingRequestGeneration = useRef(0);
  const actorUserId = session.user?.id || '';
  const loadSupporting = useCallback(async (signal?: AbortSignal) => {
    const generation = ++supportingRequestGeneration.current;
    const isCurrent = () => supportingRequestGeneration.current === generation && !signal?.aborted;
    if (isCurrent()) { setLoading(true); setSupportingReady(false); }
    const [policyResult, facilityResult] = await Promise.allSettled([fetchConsentPolicies(organizationId, signal), fetchEnrollmentFacilities(organizationId, signal)]);
    if (!isCurrent()) return;
    if (policyResult.status === 'fulfilled') { setPolicies(policyResult.value); setSupportingReady(true); setSupportError(''); } else { setSupportingReady(false); setSupportError(errorMessage(policyResult.reason)); }
    if (facilityResult.status === 'fulfilled') setFacilities(facilityResult.value); else setFacilities([]);
    setLoading(false);
  }, [organizationId]);
  useEffect(() => {
    const controller = new AbortController();
    void loadSupporting(controller.signal);
    return () => {
      controller.abort();
      supportingRequestGeneration.current += 1;
    };
  }, [loadSupporting]);
  useRealtimeRefresh({ scope: 'family-authority-decisions', organizationId, enabled: true, entityTypes: ['release_authorization', 'release_rule', 'consent', 'consent_policy', 'child_consent_decision', 'child_authority_head'], refresh: async () => { await Promise.all([loadSupporting(), onWorkspaceChanged()]); } });
  const mutationLocked = childcareMutationControlDisabled(recovery.laneBlocked, busy, parentBusy, !actorUserId, !supportingReady);
  const focusedRecordExists = focus ? authorityWorkspaceFocusExists(workspace, focus) : true;

  useEffect(() => {
    if (!focus || !focusedRecordExists || !focusedRecordRef.current) return;
    const frame = window.requestAnimationFrame(() => {
      focusedRecordRef.current?.scrollIntoView({ behavior: motionAllowed ? 'smooth' : 'auto', block: 'center' });
      focusedRecordRef.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focus?.id, focus?.kind, focusedRecordExists, motionAllowed, workspace]);

  const run = async <Result extends MutationResult>(metadata: ChildcareMutationMetadata, send: (operationId: string) => Promise<Result>, success: string): Promise<void> => {
    setBusy(true); setError(''); setNotice('');
    try {
      await recovery.execute(metadata, send);
      await Promise.all([onWorkspaceChanged(), loadSupporting()]); setNotice(success); setDialog(null);
    } catch (caught) {
      if (caught instanceof ChildcareCommandRecoveredCommitError) { await Promise.all([onWorkspaceChanged(), loadSupporting()]); setNotice('CareSync confirmed the interrupted authority decision was saved.'); setDialog(null); }
      else { setError(errorMessage(caught)); requestAnimationFrame(() => errorRef.current?.focus()); }
    } finally { setBusy(false); }
  };

  const submit = async (input: Record<string, unknown>) => {
    if (!dialog) return;
    const operation = createClientOperationId();
    if (dialog.kind === 'policy') {
      await run({ clientOperationId: operation, commandType: 'organization.consent.policy.publish', targetType: 'consent', expectedTargetId: null, expectedActionOwnerId: null }, (id) => publishConsentPolicy(input as never, organizationId, id), 'The immutable consent-policy version was published. It does not itself record a child decision.'); return;
    }
    const child = dialog.child; const expected = child.authority_revision;
    if (dialog.kind === 'grant') {
      await run({ clientOperationId: operation, commandType: 'child.release.authorization.grant', targetType: 'release_authorization', expectedTargetId: null, expectedActionOwnerId: child.child_id }, (id) => grantReleaseAuthorization(child.child_id, { expected_authority_revision: expected, ...input } as never, organizationId, id), RELEASE_AUTHORIZATION_SAVED_COPY); return;
    }
    if (dialog.kind === 'rule') {
      await run({ clientOperationId: operation, commandType: 'child.release.rule.create', targetType: 'release_rule', expectedTargetId: null, expectedActionOwnerId: child.child_id }, (id) => createReleaseRule(child.child_id, { expected_authority_revision: expected, ...input } as never, organizationId, id), 'The release restriction was recorded with an educator-safe explanation code. Checkout enforcement remains staged.'); return;
    }
    if (dialog.kind === 'consent') {
      await run({ clientOperationId: operation, commandType: 'child.consent.record', targetType: 'consent', expectedTargetId: null, expectedActionOwnerId: child.child_id }, (id) => recordChildConsent(child.child_id, { expected_authority_revision: expected, ...input } as never, organizationId, id), 'The policy-bound child consent decision was recorded. It does not activate unrelated care workflows.'); return;
    }
    const reason = String(input.reason_code);
    if (dialog.kind === 'revoke_authorization') {
      await run({ clientOperationId: operation, commandType: 'child.release.authorization.revoke', targetType: 'release_authorization', expectedTargetId: dialog.record.id, expectedActionOwnerId: child.child_id }, (id) => revokeReleaseAuthorization(child.child_id, dialog.record.id, dialog.record.version, expected, reason as never, organizationId, id), 'The release authorization was revoked. Historical evidence remains intact.'); return;
    }
    if (dialog.kind === 'revoke_rule') {
      await run({ clientOperationId: operation, commandType: 'child.release.rule.revoke', targetType: 'release_rule', expectedTargetId: dialog.record.id, expectedActionOwnerId: child.child_id }, (id) => revokeReleaseRule(child.child_id, dialog.record.id, dialog.record.version, expected, reason as never, organizationId, id), 'The release restriction was revoked. Historical evidence remains intact.'); return;
    }
    await run({ clientOperationId: operation, commandType: 'child.consent.withdraw', targetType: 'consent', expectedTargetId: dialog.record.id, expectedActionOwnerId: child.child_id }, (id) => withdrawChildConsent(child.child_id, dialog.record.id, dialog.record.version, expected, reason as never, organizationId, id), 'The consent decision was withdrawn. A later correction requires a new decision.');
  };

  const childById = new Map(family.children.map((child) => [child.id, child])); const people = activeAuthorityPeople(workspace);
  return <Shell>
    <Notice><ExclamationTriangleIcon /><span><strong>Release authority records.</strong> {RELEASE_AUTHORITY_BOUNDARY_COPY}</span></Notice>
    {focus && !focusedRecordExists && <Notice role="status"><ExclamationTriangleIcon /> The exact release or consent record is not present in this family workspace. CareSync did not select another record.</Notice>}
    {notice && <Notice $success role="status" aria-live="polite"><CheckCircleIcon /> {notice}</Notice>}
    {supportError && <Notice $error role="alert"><ExclamationTriangleIcon /> {supportError}</Notice>}
    {error && <Notice ref={errorRef} tabIndex={-1} $error role="alert"><ExclamationTriangleIcon /> {error}</Notice>}
    <Block $accent="cyan" $tone="positive"><Head><div><Eyebrow><KeyIcon width={14} /> Positive release grants</Eyebrow><h3>Who may receive each child</h3><p>Positive authorization is separate from restrictions. Every grant binds one current recipient, grantor version, reviewed basis, verification policy, and finite window.</p></div></Head><ChildGrid>{workspace.children.map((child) => { const profile = childById.get(child.child_id); return <ChildCard key={child.child_id}><CardHead><div><strong>{profile ? `${profile.first_name} ${profile.last_name}` : 'Protected child record'}</strong><small>Authority revision {child.authority_revision}</small></div><ActionButton type="button" $variant="primary" disabled={mutationLocked || !profile} onClick={() => { setError(''); setDialog({ kind: 'grant', child }); }}><PlusIcon /> Grant</ActionButton></CardHead><Rows>{child.release_authorizations.length ? child.release_authorizations.map((record) => { const state = effectiveRecordState(record); const focused = focus?.kind === 'release_authorization' && focus.id === record.id; return <Row id={`authority-release_authorization-${record.id}`} key={record.id} ref={focused ? focusedRecordRef : undefined} tabIndex={focused ? -1 : undefined} $focused={focused}><header><div><strong>{personName(workspace.people.find((person) => person.id === record.recipient_person_id))}</strong><small>{authorityLabel(record.verification_policy_code)}</small></div><StatusChip $tone={statusTone(state)}>{authorityLabel(state)}</StatusChip></header><small>{dateTimeLabel(record.effective_from)} → {dateTimeLabel(record.effective_until)}</small>{!record.revoked_at && <Actions><ActionButton type="button" $variant="danger" disabled={mutationLocked || !profile} onClick={() => setDialog({ kind: 'revoke_authorization', child, record })}>Revoke</ActionButton></Actions>}</Row>; }) : <Empty>No positive release authorization has been recorded.</Empty>}</Rows></ChildCard>; })}</ChildGrid></Block>
    <Block $accent="plasma" $tone="restriction"><Head><div><Eyebrow><ShieldExclamationIcon width={14} /> Release restrictions</Eyebrow><h3>Safety restrictions and manager review</h3><p>Restrictions never create a positive grant. This activation slice permits only deny and manager-review rules; confidential reasons stay inside this admin workspace.</p></div></Head><ChildGrid>{workspace.children.map((child) => { const profile = childById.get(child.child_id); return <ChildCard key={child.child_id}><CardHead><div><strong>{profile ? `${profile.first_name} ${profile.last_name}` : 'Protected child record'}</strong><small>{child.release_rules.length} rule record(s)</small></div><ActionButton type="button" $variant="danger" disabled={mutationLocked || !profile} onClick={() => { setError(''); setDialog({ kind: 'rule', child }); }}><PlusIcon /> Restriction</ActionButton></CardHead><Rows>{child.release_rules.length ? child.release_rules.map((record) => { const state = effectiveRecordState(record); const focused = focus?.kind === 'release_rule' && focus.id === record.id; return <Row id={`authority-release_rule-${record.id}`} key={record.id} ref={focused ? focusedRecordRef : undefined} tabIndex={focused ? -1 : undefined} $focused={focused}><header><div><strong>{authorityLabel(record.rule_kind)}</strong><small>{authorityLabel(record.safe_explanation_code)} · {authorityLabel(record.scope.kind)}</small></div><StatusChip $tone={statusTone(state)}>{authorityLabel(state)}</StatusChip></header><small>{dateTimeLabel(record.effective_from)} → {dateTimeLabel(record.effective_until)}</small><small>Confidential admin reason: {record.confidential_reason}</small>{!record.revoked_at && <Actions><ActionButton type="button" $variant="danger" disabled={mutationLocked || !profile} onClick={() => setDialog({ kind: 'revoke_rule', child, record })}>Revoke</ActionButton></Actions>}</Row>; }) : <Empty>No release restriction has been recorded.</Empty>}</Rows></ChildCard>; })}</ChildGrid></Block>
    <Block $accent="cyan" $tone="consent"><Head><div><Eyebrow><HandRaisedIcon width={14} /> Policy-bound consent</Eyebrow><h3>Consent policies and child decisions</h3><p>Policy publication is organization-wide. Each child decision uses two distinct reviewed evidence tuples: signer authority and signed consent.</p></div><ActionButton type="button" $variant="primary" disabled={mutationLocked || loading} onClick={() => { setError(''); setDialog({ kind: 'policy' }); }}><PlusIcon /> Publish policy</ActionButton></Head><Rows>{policies.length ? policies.map((policy) => { const state = effectiveRecordState(policy); return <Row key={policy.id}><header><div><strong>{policy.title}</strong><small>{authorityLabel(policy.purpose_code)} · version {policy.version_number} · {authorityLabel(policy.signer_authority_requirement)}</small></div><StatusChip $tone={statusTone(state)}>{authorityLabel(state)}</StatusChip></header><small>{dateTimeLabel(policy.effective_from)} → {dateTimeLabel(policy.effective_until)} · content digest {policy.content_sha256.slice(0, 10)}…</small><PolicyDetails><summary>Read exact immutable policy content</summary><PolicyText>{policy.content_text}</PolicyText></PolicyDetails></Row>; }) : <Empty>{loading ? 'Loading consent policies…' : 'No immutable consent-policy version has been published.'}</Empty>}</Rows><ChildGrid>{workspace.children.map((child) => { const profile = childById.get(child.child_id); return <ChildCard key={child.child_id}><CardHead><div><strong>{profile ? `${profile.first_name} ${profile.last_name}` : 'Protected child record'}</strong><small>{child.consent_decisions.length} consent decision(s)</small></div><ActionButton type="button" $variant="primary" disabled={mutationLocked || !profile || currentConsentPolicies(policies).length === 0} onClick={() => { setError(''); setDialog({ kind: 'consent', child }); }}><PlusIcon /> Record</ActionButton></CardHead><Rows>{child.consent_decisions.length ? child.consent_decisions.map((record) => { const state = effectiveRecordState(record); const policy = policies.find((item) => item.id === record.policy_version_id); const focused = focus?.kind === 'consent' && focus.id === record.id; return <Row id={`authority-consent-${record.id}`} key={record.id} ref={focused ? focusedRecordRef : undefined} tabIndex={focused ? -1 : undefined} $focused={focused}><header><div><strong>{policy?.title || authorityLabel(record.purpose_code)}</strong><small>{authorityLabel(record.decision)} · {authorityLabel(record.scope.kind)}</small></div><StatusChip $tone={statusTone(state)}>{authorityLabel(state)}</StatusChip></header><small>{dateTimeLabel(record.effective_from)} → {dateTimeLabel(record.effective_until)}</small>{!record.withdrawn_at && <Actions><ActionButton type="button" $variant="danger" disabled={mutationLocked || !profile} onClick={() => setDialog({ kind: 'withdraw_consent', child, record })}>Withdraw</ActionButton></Actions>}</Row>; }) : <Empty>No policy-bound consent decision has been recorded.</Empty>}</Rows></ChildCard>; })}</ChildGrid></Block>
    {dialog && <DecisionEditor key={`${dialog.kind}-${'child' in dialog ? dialog.child.child_id : 'organization'}-${'record' in dialog ? dialog.record.id : ''}`} dialog={dialog} family={family} workspace={workspace} policies={policies} facilities={facilities} actorUserId={actorUserId} busy={busy} error={error} onClose={() => setDialog(null)} onSubmit={(input) => void submit(input)} />}
  </Shell>;
}
