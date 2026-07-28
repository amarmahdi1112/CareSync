import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import styled, { keyframes } from 'styled-components';
import { ArrowPathIcon, ShieldCheckIcon } from '@heroicons/react/24/outline';
import { CareSyncMark } from '../components/brand/CareSyncMark';
import { ActionButton, GlassPanel, StatusChip } from '../components/ui/Primitives';
import { useSession } from './SessionContext';
import { resolveOnboardingState } from './routeGuardModel';

const breathe = keyframes`50% { opacity: .62; transform: scale(.96); }`;

const Gate = styled.main`
  display: grid;
  min-height: 100vh;
  padding: 24px;
  place-items: center;
`;

const GateCard = styled(GlassPanel)`
  display: grid;
  width: min(460px, 100%);
  gap: 16px;
  padding: clamp(28px, 6vw, 48px);
  text-align: center;
  > svg { width: 52px; margin: 0 auto; color: ${({ theme }) => theme.color.amber}; }
  h1 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.8rem; letter-spacing: -.05em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .78rem; line-height: 1.7; }
  button { width: 100%; }
`;

const LoadingMark = styled.div`display: grid; place-items: center; animation: ${breathe} 1.5s ease-in-out infinite;`;

function Verifying() {
  return <Gate><GateCard $accent="cyan" role="status" aria-live="polite"><LoadingMark><CareSyncMark size={58} /></LoadingMark><StatusChip $tone="info">Verifying workspace</StatusChip><h1>Preparing your secure workspace.</h1><p>CareSync is confirming your identity and organization before opening protected records.</p></GateCard></Gate>;
}

function Unavailable({ retry }: { retry: () => void }) {
  return <Gate><GateCard $accent="amber" role="alert"><ShieldCheckIcon /><StatusChip $tone="warning">Connection unavailable</StatusChip><h1>Your workspace stayed locked.</h1><p>CareSync could not confirm the saved session. No organization records were requested or changed.</p><ActionButton type="button" $variant="primary" onClick={retry}><ArrowPathIcon /> Try again</ActionButton></GateCard></Gate>;
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  if (session.status === 'checking') return <Verifying />;
  if (session.status === 'unavailable') return <Unavailable retry={session.retry} />;
  if (session.status !== 'authenticated') {
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }
  return <>{children}</>;
}

export function OnboardingGuard({ children }: { children: ReactNode }) {
  const session = useSession();
  const state = resolveOnboardingState(session.status, session.organization, session.organizationUnavailable);
  if (state === 'checking') return <Verifying />;
  if (state === 'unavailable') return <Unavailable retry={session.retry} />;
  if (state === 'required') return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}
