import { ArrowPathIcon, CheckCircleIcon, ExclamationTriangleIcon, ShieldCheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';
import styled from 'styled-components';
import { ActionButton, StatusChip } from '../components/ui/Primitives';
import {
  childcareRecoveryReasonMessage,
  useChildcareCommandRecovery,
} from './ChildcareCommandRecoveryContext';

const Surface = styled.aside`
  position: relative;
  z-index: 5;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin: 14px 18px 0;
  padding: 13px 14px;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 14px 6px 14px 6px;
  background: color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 92%, ${({ theme }) => theme.color.cyan});
  box-shadow: ${({ theme }) => theme.shadow.panel};

  > svg {
    width: 22px;
    color: ${({ theme }) => theme.color.cyan};
  }

  @media (max-width: 620px) {
    grid-template-columns: auto minmax(0, 1fr);
    margin: 10px 10px 0;
    > div:last-child { grid-column: 1 / -1; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }
`;

const Copy = styled.div`
  min-width: 0;
  h2 { margin: 0 0 3px; font-size: .82rem; font-weight: 620; letter-spacing: -.01em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.5; }
`;

const Actions = styled.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  a { text-decoration: none; }
  button, a > span { min-height: 42px; }
`;

const CloseButton = styled.button`
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 10px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  svg { width: 17px; }
`;

function targetLabel(targetType: string): string {
  if (targetType === 'family') return 'family record';
  if (targetType === 'child') return 'child record';
  if (targetType === 'enrollment') return 'child enrollment';
  if (targetType === 'admission_application') return 'admission application';
  if (targetType === 'admission_waitlist') return 'admission waitlist record';
  if (targetType === 'admission_offer') return 'admission offer record';
  if (targetType === 'authority_person') return 'family authority person';
  if (targetType === 'authority_evidence') return 'family authority evidence';
  return 'quarantined family authority document';
}

export function ChildcareCommandRecoverySurface() {
  const recovery = useChildcareCommandRecovery();
  const entry = recovery.activeEntry;

  if (entry) {
    const absent = entry.status === 'absent_final';
    return (
      <Surface role={absent ? 'alert' : 'status'} aria-live={absent ? 'assertive' : 'polite'} aria-atomic="true">
        {absent ? <ExclamationTriangleIcon aria-hidden="true" /> : <ShieldCheckIcon aria-hidden="true" />}
        <Copy>
          <h2>{absent ? 'Review this unsaved change' : 'A childcare change needs confirmation'}</h2>
          <p>{absent
            ? 'The server proved this operation did not commit. Review the form again before allowing a new operation ID; CareSync will never resend it automatically.'
            : childcareRecoveryReasonMessage(recovery.blockReason)}</p>
        </Copy>
        <Actions>
          <StatusChip $tone={absent ? 'warning' : 'info'}>{recovery.checking ? 'Checking…' : absent ? 'Not saved' : 'Held safely'}</StatusChip>
          {absent
            ? <ActionButton type="button" $variant="primary" onClick={() => void recovery.acknowledgeFinalAbsence()} disabled={recovery.checking}>I reviewed it — allow a new change</ActionButton>
            : <ActionButton type="button" $variant="primary" onClick={() => void recovery.checkSavedResult()} disabled={recovery.checking}><ArrowPathIcon aria-hidden="true" /> Check saved result</ActionButton>}
        </Actions>
      </Surface>
    );
  }

  if (recovery.lastResolved) {
    return (
      <Surface role="status" aria-live="polite" aria-atomic="true">
        <CheckCircleIcon aria-hidden="true" />
        <Copy>
          <h2>Saved result confirmed</h2>
          <p>CareSync matched the receipt and refreshed the canonical {targetLabel(recovery.lastResolved.targetType)} at version {recovery.lastResolved.version}.</p>
        </Copy>
        <Actions>
          <Link to={recovery.lastResolved.actionRoute} onClick={recovery.dismissResolved}><ActionButton as="span" $variant="primary">Open saved record</ActionButton></Link>
          <CloseButton type="button" aria-label="Dismiss saved result" onClick={recovery.dismissResolved}><XMarkIcon aria-hidden="true" /></CloseButton>
        </Actions>
      </Surface>
    );
  }

  if (recovery.blockReason) {
    return (
      <Surface role="alert" aria-live="assertive" aria-atomic="true">
        <ExclamationTriangleIcon aria-hidden="true" />
        <Copy>
          <h2>Childcare changes are paused</h2>
          <p>{childcareRecoveryReasonMessage(recovery.blockReason)} No family, child, enrollment, or placement mutation will be sent until this check passes.</p>
        </Copy>
        <Actions>
          <ActionButton type="button" $variant="primary" onClick={() => void recovery.checkSavedResult()} disabled={recovery.checking}><ArrowPathIcon aria-hidden="true" /> Check durable lane</ActionButton>
        </Actions>
      </Surface>
    );
  }

  return null;
}
