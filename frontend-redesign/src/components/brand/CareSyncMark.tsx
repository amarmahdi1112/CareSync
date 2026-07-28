import { useId } from 'react';
import { useTheme } from 'styled-components';
import { useMotion } from '../../motion';

interface CareSyncMarkProps {
  size?: number;
  animated?: boolean;
}

export function CareSyncMark({ size = 42, animated = true }: CareSyncMarkProps) {
  const id = useId().replace(/:/g, '');
  const theme = useTheme();
  const { autonomousAllowed } = useMotion();
  const workspace = theme.mode === 'workspace';
  const palette = workspace
    ? {
        coreStart: theme.color.plasmaBright,
        coreMiddle: theme.color.cyan,
        coreEnd: theme.color.plasma,
        glow: theme.color.cyan,
        disc: theme.color.canvasElevated,
        stroke: theme.color.borderStrong,
        orbit: theme.color.cyan,
        signal: theme.color.amber,
      }
    : {
        coreStart: '#d7c2ff',
        coreMiddle: '#a978ff',
        coreEnd: '#53e6ff',
        glow: '#a978ff',
        disc: '#0b1020',
        stroke: 'rgba(192,168,255,.36)',
        orbit: '#53e6ff',
        signal: '#ffca72',
      };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      aria-hidden="true"
      focusable="false"
      style={{ overflow: 'visible' }}
    >
      <defs>
        <linearGradient id={`${id}-core`} x1="8" y1="4" x2="40" y2="44" gradientUnits="userSpaceOnUse">
          <stop stopColor={palette.coreStart} />
          <stop offset="0.48" stopColor={palette.coreMiddle} />
          <stop offset="1" stopColor={palette.coreEnd} />
        </linearGradient>
        <radialGradient id={`${id}-glow`} cx="0" cy="0" r="1" gradientTransform="translate(24 24) rotate(90) scale(21)">
          <stop stopColor={palette.glow} stopOpacity={workspace ? '.22' : '.36'} />
          <stop offset="1" stopColor={palette.glow} stopOpacity="0" />
        </radialGradient>
        <filter id={`${id}-blur`} x="-70%" y="-70%" width="240%" height="240%">
          <feGaussianBlur stdDeviation="3.4" />
        </filter>
      </defs>
      <circle cx="24" cy="24" r="21" fill={`url(#${id}-glow)`} filter={`url(#${id}-blur)`} />
      <circle cx="24" cy="24" r="18.4" fill={palette.disc} stroke={palette.stroke} strokeWidth="1" />
      <ellipse
        cx="24"
        cy="24"
        rx="21"
        ry="8.3"
        fill="none"
        stroke={palette.orbit}
        strokeOpacity=".7"
        strokeWidth="1.2"
        strokeDasharray="4 5"
      >
        {animated && autonomousAllowed && <animateTransform attributeName="transform" type="rotate" from="0 24 24" to="360 24 24" dur="14s" repeatCount="indefinite" />}
      </ellipse>
      <path
        d="M14.2 25.3c3.5 0 5.7-1.2 7.9-3.2l2.1-2c2.4-2.2 4.7-3.7 8.9-3.7 1.2 0 2.3.2 3.3.6-2.3-3.7-6.4-6.2-11.1-6.2-7.2 0-13.1 5.8-13.1 13 0 .5 0 1 .1 1.5h1.9Z"
        fill={`url(#${id}-core)`}
      />
      <path
        d="M33.8 22.7c-3.5 0-5.7 1.2-7.9 3.2l-2.1 2c-2.4 2.2-4.7 3.7-8.9 3.7-1.2 0-2.3-.2-3.3-.6 2.3 3.7 6.4 6.2 11.1 6.2 7.2 0 13.1-5.8 13.1-13 0-.5 0-1-.1-1.5h-1.9Z"
        fill={`url(#${id}-core)`}
        opacity=".82"
      />
      <circle cx="31.4" cy="12.8" r="2.2" fill={palette.signal} />
    </svg>
  );
}
