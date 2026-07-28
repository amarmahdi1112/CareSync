import { XMarkIcon } from "@heroicons/react/24/outline";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { IconButton } from "../../components/ui/Primitives";

const Backdrop = styled.div`
  position: fixed;
  inset: 0;
  z-index: 980;
  display: grid;
  place-items: center;
  padding: max(18px, env(safe-area-inset-top))
    max(14px, env(safe-area-inset-right)) max(18px, env(safe-area-inset-bottom))
    max(14px, env(safe-area-inset-left));
  background: rgba(2, 7, 17, 0.76);
  backdrop-filter: blur(9px);
`;
const Surface = styled.section`
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  width: min(650px, 100%);
  max-height: calc(
    100dvh - max(36px, env(safe-area-inset-top) + env(safe-area-inset-bottom))
  );
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 18px 7px 18px 7px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.surfaceStrong};
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.55);
  > header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding: 18px 18px 14px;
    border-bottom: 1px solid ${({ theme }) => theme.color.divider};
  }
  h2 {
    margin: 0 0 5px;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.08rem;
    font-weight: 560;
    letter-spacing: -0.02em;
  }
  p {
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.7rem;
    line-height: 1.55;
  }
`;
const Body = styled.fieldset`
  min-height: 0;
  min-inline-size: 0;
  margin: 0;
  border: 0;
  padding: 18px;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
`;
const Footer = styled.footer`
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding: 13px 18px;
  border-top: 1px solid ${({ theme }) => theme.color.divider};
  background: rgba(0, 0, 0, 0.08);
`;

export function BillingDialog({
  title,
  description,
  children,
  footer,
  busy = false,
  onClose,
}: {
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
  busy?: boolean;
  onClose: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const surface = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    opener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = surface.current?.querySelector<HTMLElement>(
      "input,select,textarea,button:not([disabled])",
    );
    first?.focus();
    return () => {
      document.body.style.overflow = previous;
      if (opener.current?.isConnected) opener.current.focus();
    };
  }, []);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
      if (event.key !== "Tab" || !surface.current) return;
      const controls = [
        ...surface.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
        ),
      ];
      if (!controls.length) return;
      const firstControl = controls[0];
      const lastControl = controls.at(-1)!;
      if (event.shiftKey && document.activeElement === firstControl) {
        event.preventDefault();
        lastControl.focus();
      } else if (!event.shiftKey && document.activeElement === lastControl) {
        event.preventDefault();
        firstControl.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
    };
  }, [busy, onClose]);
  return createPortal(
    <Backdrop
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <Surface
        ref={surface}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy}
      >
        <header>
          <div>
            <h2 id={titleId}>{title}</h2>
            <p id={descriptionId}>{description}</p>
          </div>
          <IconButton
            type="button"
            aria-label="Close dialog"
            onClick={onClose}
            disabled={busy}
          >
            <XMarkIcon />
          </IconButton>
        </header>
        <Body disabled={busy}>{children}</Body>
        <Footer>{footer}</Footer>
      </Surface>
    </Backdrop>,
    document.body,
  );
}
