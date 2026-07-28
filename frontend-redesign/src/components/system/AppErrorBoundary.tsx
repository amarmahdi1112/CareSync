import { Component, type ErrorInfo, type ReactNode } from 'react';
import styled from 'styled-components';
import { ArrowPathIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { ActionButton, Eyebrow, GlassPanel } from '../ui/Primitives';
import { APP_RECOVERY_COPY } from '../../config/activeRuntimeCopy';

const Screen = styled.main`
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 24px;
`;

const Card = styled(GlassPanel)`
  width: min(620px, 100%);
  padding: clamp(26px, 5vw, 52px);
  text-align: center;
  > svg { width: 52px; margin: 0 auto 19px; color: ${({ theme }) => theme.color.coral}; }
  h1 { margin: 13px 0 9px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2rem, 5vw, 3.5rem); font-weight: 520; letter-spacing: -.065em; }
  p { max-width: 490px; margin: 0 auto 24px; color: ${({ theme }) => theme.color.textMuted}; font-size: .78rem; line-height: 1.7; }
`;

interface BoundaryState {
  failed: boolean;
}

export class AppErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) console.error('CareSync redesign render failure', error, info);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Screen role="alert">
        <Card $accent="plasma">
          <ExclamationTriangleIcon aria-hidden="true" />
          <Eyebrow>Interface recovery gate</Eyebrow>
          <h1>The command surface lost sync.</h1>
          <p>{APP_RECOVERY_COPY}</p>
          <ActionButton $variant="primary" onClick={() => window.location.reload()}><ArrowPathIcon /> Reload interface</ActionButton>
        </Card>
      </Screen>
    );
  }
}
