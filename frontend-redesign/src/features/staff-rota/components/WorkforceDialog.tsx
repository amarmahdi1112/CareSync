import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import styled from 'styled-components';
import { GlassPanel } from '../../../components/ui/Primitives';

export const WorkforceModalOverlay = styled.div`
  position:fixed;inset:0;z-index:940;display:flex;width:100%;height:100vh;height:100dvh;min-width:0;align-items:flex-start;justify-content:center;
  padding:max(18px,env(safe-area-inset-top)) max(18px,env(safe-area-inset-right)) max(18px,env(safe-area-inset-bottom)) max(18px,env(safe-area-inset-left));
  overflow:hidden;overscroll-behavior:contain;
  background:${({ theme }) => theme.color.overlay};backdrop-filter:blur(${({ theme }) => theme.effect.overlayBlur});
  @media(max-width:720px){padding:max(8px,env(safe-area-inset-top)) max(8px,env(safe-area-inset-right)) max(8px,env(safe-area-inset-bottom)) max(8px,env(safe-area-inset-left));}
`;

export const WorkforceModalSurface = styled(GlassPanel)`
  width:min(780px,100%);max-height:100%;flex:0 1 auto;margin-block:auto;padding:20px;overflow-x:hidden;overflow-y:auto;
  overscroll-behavior:contain;scrollbar-gutter:stable;-webkit-overflow-scrolling:touch;
  @media(max-width:720px){width:100%;padding:18px 14px 28px;}
`;

export function WorkforceModalPortal({ children }: { children: ReactNode }) {
  useEffect(() => {
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = bodyOverflow; };
  }, []);
  if (typeof document === 'undefined') return null;
  return createPortal(children, document.body);
}

export const WorkforceDialogHeader = styled.header`
  display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:17px;
  h2{margin:7px 0 4px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.15rem,2.6vw,1.45rem);font-weight:560;letter-spacing:-.035em;}
  p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.73rem;line-height:1.55;}
`;

export const WorkforceDialogForm = styled.form`display:grid;gap:14px;`;
export const WorkforceDialogGrid = styled.div`display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;@media(max-width:570px){grid-template-columns:1fr;}`;
export const WorkforceDialogActions = styled.div`display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;padding-top:3px;@media(max-width:500px){display:grid;grid-template-columns:1fr 1fr;}@media(max-width:390px){grid-template-columns:1fr;}`;
export const WorkforceDialogField = styled.label<{ $wide?: boolean }>`
  display:grid;grid-column:${({ $wide }) => $wide ? '1/-1' : 'auto'};gap:6px;color:${({ theme }) => theme.color.textSoft};font-size:.7rem;font-weight:600;
  input,select,textarea{width:100%;min-height:44px;padding:0 11px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:9px 12px 9px 12px;outline:0;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;}
  textarea{min-height:88px;padding:10px;resize:vertical;}
  input:focus,select:focus,textarea:focus{border-color:${({ theme }) => theme.color.cyan};}
  small{color:${({ theme }) => theme.color.textMuted};font-size:.66rem;font-weight:400;line-height:1.45;}
`;

export function WorkforceDialog({
  children,
  busy = false,
  retryLocked = false,
  onClose,
  labelId,
}: {
  children: ReactNode;
  busy?: boolean;
  retryLocked?: boolean;
  onClose: () => void;
  labelId: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  const lockedRef = useRef(busy || retryLocked);
  closeRef.current = onClose;
  lockedRef.current = busy || retryLocked;

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !lockedRef.current) closeRef.current();
      if (event.key !== 'Tab' || !ref.current) return;
      const focusable = [...ref.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])',
      )];
      if (!focusable.length) return;
      const first = focusable[0]!;
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input:not(:disabled),select:not(:disabled),textarea:not(:disabled),button:not(:disabled)')?.focus({ preventScroll: true }));
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);

  return <WorkforceModalPortal>
    <WorkforceModalOverlay onMouseDown={(event) => { if (event.target === event.currentTarget && !busy && !retryLocked) onClose(); }}>
      <WorkforceModalSurface ref={ref} $accent="cyan" role="dialog" aria-modal="true" aria-labelledby={labelId} aria-busy={busy || retryLocked}>
        {children}
      </WorkforceModalSurface>
    </WorkforceModalOverlay>
  </WorkforceModalPortal>;
}
