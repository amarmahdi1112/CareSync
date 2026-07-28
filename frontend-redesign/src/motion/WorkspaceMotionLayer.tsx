import { useEffect, useRef } from 'react';
import styled from 'styled-components';
import { useMotion } from './MotionProvider';

const Layer = styled.div<{ $interactive: boolean }>`
  --caresync-ice-x: 0px;
  --caresync-ice-y: 0px;
  --caresync-violet-x: 0px;
  --caresync-violet-y: 0px;
  --caresync-refraction-x: 72%;
  --caresync-refraction-y: 18%;

  position: absolute;
  z-index: 0;
  inset: 0;
  overflow: hidden;
  contain: layout paint style;
  pointer-events: none;

  html[data-caresync-motion='off'] & {
    opacity: 0;
  }

  html[data-caresync-motion='reduced'] &,
  html[data-caresync-motion='paused'] & {
    --caresync-ice-x: 0px;
    --caresync-ice-y: 0px;
    --caresync-violet-x: 0px;
    --caresync-violet-y: 0px;
    --caresync-refraction-x: 72%;
    --caresync-refraction-y: 18%;
  }

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) {
    opacity: .72;
  }
`;

const IceField = styled.div`
  position: absolute;
  top: -15rem;
  right: -16rem;
  width: min(78vw, 66rem);
  height: min(66vw, 48rem);
  border-radius: 50%;
  opacity: .2;
  background: radial-gradient(
    ellipse at center,
    color-mix(in srgb, ${({ theme }) => theme.color.cyan} 54%, transparent),
    color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 16%, transparent) 38%,
    transparent 72%
  );
  filter: blur(22px);
  transform: translate3d(var(--caresync-ice-x), var(--caresync-ice-y), 0) rotate(-8deg);
  transition: transform 160ms ${({ theme }) => theme.motion.ease};

  html[data-caresync-motion='reduced'] &,
  html[data-caresync-motion='off'] &,
  html[data-caresync-motion='paused'] & {
    transition: none;
  }
`;

const VioletField = styled.div`
  position: absolute;
  bottom: -20rem;
  left: -12rem;
  width: min(72vw, 60rem);
  height: min(62vw, 44rem);
  border-radius: 50%;
  opacity: .16;
  background: radial-gradient(
    ellipse at center,
    color-mix(in srgb, ${({ theme }) => theme.color.plasma} 48%, transparent),
    color-mix(in srgb, ${({ theme }) => theme.color.cyan} 12%, transparent) 44%,
    transparent 73%
  );
  filter: blur(26px);
  transform: translate3d(var(--caresync-violet-x), var(--caresync-violet-y), 0) rotate(12deg);
  transition: transform 180ms ${({ theme }) => theme.motion.ease};

  html[data-caresync-motion='reduced'] &,
  html[data-caresync-motion='off'] &,
  html[data-caresync-motion='paused'] & {
    transition: none;
  }
`;

const Refraction = styled.div<{ $interactive: boolean }>`
  position: absolute;
  inset: 0;
  opacity: ${({ $interactive }) => $interactive ? .62 : 0};
  background: radial-gradient(
    circle 12rem at var(--caresync-refraction-x) var(--caresync-refraction-y),
    color-mix(in srgb, ${({ theme }) => theme.color.plasmaBright} 8%, transparent),
    color-mix(in srgb, ${({ theme }) => theme.color.cyan} 3%, transparent) 42%,
    transparent 74%
  );
  transition: opacity 160ms ease;

  html[data-caresync-motion='reduced'] &,
  html[data-caresync-motion='off'] &,
  html[data-caresync-motion='paused'] & {
    opacity: 0;
    transition: none;
  }
`;

interface PointerPosition {
  clientX: number;
  clientY: number;
}

function resetLayerVariables(node: HTMLDivElement): void {
  node.style.removeProperty('--caresync-ice-x');
  node.style.removeProperty('--caresync-ice-y');
  node.style.removeProperty('--caresync-violet-x');
  node.style.removeProperty('--caresync-violet-y');
  node.style.removeProperty('--caresync-refraction-x');
  node.style.removeProperty('--caresync-refraction-y');
}

export function WorkspaceMotionLayer() {
  const layerRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const pointerRef = useRef<PointerPosition>({ clientX: 0, clientY: 0 });
  const { autonomousAllowed, finePointer } = useMotion();
  const interactive = autonomousAllowed && finePointer;

  useEffect(() => {
    const node = layerRef.current;
    if (!node) return;

    const cancelFrame = () => {
      if (frameRef.current === null) return;
      window.cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };

    const commitPointer = () => {
      frameRef.current = null;
      const bounds = node.getBoundingClientRect();
      const width = Math.max(bounds.width, 1);
      const height = Math.max(bounds.height, 1);
      const x = Math.min(Math.max((pointerRef.current.clientX - bounds.left) / width, 0), 1);
      const y = Math.min(Math.max((pointerRef.current.clientY - bounds.top) / height, 0), 1);
      const horizontal = x - .5;
      const vertical = y - .5;

      node.style.setProperty('--caresync-ice-x', `${(horizontal * 13).toFixed(2)}px`);
      node.style.setProperty('--caresync-ice-y', `${(vertical * 9).toFixed(2)}px`);
      node.style.setProperty('--caresync-violet-x', `${(horizontal * -9).toFixed(2)}px`);
      node.style.setProperty('--caresync-violet-y', `${(vertical * -7).toFixed(2)}px`);
      node.style.setProperty('--caresync-refraction-x', `${(x * 100).toFixed(2)}%`);
      node.style.setProperty('--caresync-refraction-y', `${(y * 100).toFixed(2)}%`);
    };

    const scheduleCommit = () => {
      if (frameRef.current !== null) return;
      frameRef.current = window.requestAnimationFrame(commitPointer);
    };

    const handlePointerMove = (event: PointerEvent) => {
      pointerRef.current = { clientX: event.clientX, clientY: event.clientY };
      scheduleCommit();
    };

    const recenter = () => {
      const bounds = node.getBoundingClientRect();
      const visibleTop = Math.max(bounds.top, 0);
      const visibleRight = Math.min(bounds.right, window.innerWidth);
      const visibleBottom = Math.min(bounds.bottom, window.innerHeight);
      pointerRef.current = {
        clientX: bounds.left + Math.max(visibleRight - bounds.left, 1) * .72,
        clientY: visibleTop + Math.max(visibleBottom - visibleTop, 1) * .18,
      };
      scheduleCommit();
    };

    if (!interactive) {
      cancelFrame();
      resetLayerVariables(node);
      return () => resetLayerVariables(node);
    }

    recenter();
    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    window.addEventListener('blur', recenter);
    window.addEventListener('resize', recenter);
    window.addEventListener('scroll', scheduleCommit, { passive: true });
    document.addEventListener('pointerleave', recenter);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('blur', recenter);
      window.removeEventListener('resize', recenter);
      window.removeEventListener('scroll', scheduleCommit);
      document.removeEventListener('pointerleave', recenter);
      cancelFrame();
      resetLayerVariables(node);
    };
  }, [interactive]);

  return (
    <Layer
      ref={layerRef}
      $interactive={interactive}
      data-caresync-workspace-motion
      aria-hidden="true"
    >
      <IceField />
      <VioletField />
      <Refraction $interactive={interactive} />
    </Layer>
  );
}
