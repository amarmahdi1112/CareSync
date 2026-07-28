import { useEffect, useRef, type ReactNode } from 'react';
import styled from 'styled-components';
import { GlassPanel } from '../../components/ui/Primitives';

const Overlay = styled.div`
  position: fixed;
  inset: 0;
  z-index: 950;
  display: grid;
  place-items: center;
  padding: 18px;
  overflow-y: auto;
  background: ${({ theme }) => theme.color.overlay};
  backdrop-filter: blur(${({ theme }) => theme.effect.overlayBlur});

  @media (max-width: 720px) { padding: 0; align-items: stretch; }
`;

const Dialog = styled(GlassPanel)`
  width: min(760px, 100%);
  max-height: calc(100vh - 36px);
  padding: 22px;
  overflow-y: auto;

  @media (max-width: 720px) {
    width: 100%;
    max-height: none;
    min-height: 100dvh;
    padding: 18px 15px 28px;
    border: 0;
    border-radius: 0;
  }
`;

export const OperationDialogHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 19px;

  h2 { margin: 8px 0 5px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.35rem, 3vw, 1.75rem); font-weight: 540; letter-spacing: -.04em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .76rem; line-height: 1.6; }
`;

export const OperationForm = styled.form`display: grid; gap: 14px;`;
export const OperationFormGrid = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; @media (max-width: 560px) { grid-template-columns: 1fr; }`;
export const OperationDialogActions = styled.div`display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; padding-top: 3px; @media (max-width: 520px) { display: grid; grid-template-columns: 1fr 1fr; } @media (max-width: 390px) { grid-template-columns: 1fr; }`;

export function OperationDialog({
  children,
  busy = false,
  onClose,
  labelId,
}: {
  children: ReactNode;
  busy?: boolean;
  onClose: () => void;
  labelId: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busyRef.current) closeRef.current();
      if (event.key !== 'Tab' || !ref.current) return;
      const focusable = [...ref.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener('keydown', keydown);
    requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input, select, textarea, button')?.focus());
    return () => {
      window.removeEventListener('keydown', keydown);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  return (
    <Overlay onMouseDown={(event) => event.target === event.currentTarget && !busy && onClose()}>
      <Dialog ref={ref} $accent="cyan" role="dialog" aria-modal="true" aria-labelledby={labelId} aria-busy={busy}>
        {children}
      </Dialog>
    </Overlay>
  );
}
