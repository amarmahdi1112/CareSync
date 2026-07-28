import { createGlobalStyle, keyframes } from 'styled-components';
import { workspaceTheme } from './theme';

const drift = keyframes`
  0% { transform: translate3d(-2%, -1%, 0) scale(1); }
  50% { transform: translate3d(2%, 2%, 0) scale(1.04); }
  100% { transform: translate3d(-2%, -1%, 0) scale(1); }
`;

export const GlobalStyle = createGlobalStyle`
  @font-face {
    font-family: 'CareSync Display';
    src: url('/fonts/Comfortaa-VariableFont_wght.ttf') format('truetype');
    font-weight: 300 700;
    font-display: swap;
  }

  *, *::before, *::after { box-sizing: border-box; }

  html {
    background: ${({ theme }) => theme.color.canvas};
    color-scheme: dark;
    font-synthesis: none;
    text-rendering: optimizeLegibility;
  }

  html[data-caresync-theme='workspace'] {
    background: ${workspaceTheme.color.canvas};
    color-scheme: dark;
  }

  html, body, #root { min-height: 100%; margin: 0; }

  body {
    min-width: 320px;
    overflow-x: hidden;
    color: ${({ theme }) => theme.color.text};
    background:
      radial-gradient(circle at 79% -12%, rgba(126, 85, 222, 0.24), transparent 34rem),
      radial-gradient(circle at 14% 72%, rgba(38, 178, 209, 0.10), transparent 31rem),
      ${({ theme }) => theme.color.canvas};
    font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.5;
  }

  body[data-caresync-theme='workspace'] {
    color: ${workspaceTheme.color.text};
    background:
      radial-gradient(ellipse at 16% -10%, rgba(123,211,240,.09), transparent 36rem),
      radial-gradient(ellipse at 91% 18%, rgba(168,140,242,.07), transparent 40rem),
      linear-gradient(155deg, rgba(199,240,252,.018), transparent 42rem),
      ${workspaceTheme.color.canvas};
  }

  body::before {
    position: fixed;
    inset: -18%;
    z-index: -2;
    content: '';
    opacity: 0.46;
    pointer-events: none;
    background-image:
      radial-gradient(circle at 17% 24%, rgba(255,255,255,.8) 0 1px, transparent 1.4px),
      radial-gradient(circle at 66% 13%, rgba(144,221,255,.7) 0 1px, transparent 1.3px),
      radial-gradient(circle at 83% 74%, rgba(210,187,255,.7) 0 1px, transparent 1.2px),
      radial-gradient(circle at 42% 84%, rgba(255,255,255,.5) 0 1px, transparent 1.2px);
    background-size: 190px 190px, 260px 260px, 310px 310px, 230px 230px;
    animation: ${drift} 32s linear infinite;
  }

  body[data-caresync-theme='workspace']::before {
    opacity: 0;
    animation: none;
  }

  body[data-caresync-theme='workspace'] ::selection {
    color: ${workspaceTheme.color.ink};
    background: ${workspaceTheme.color.plasma};
  }

  body[data-caresync-theme='workspace'] :focus-visible {
    outline: 2px solid ${workspaceTheme.color.cyan};
    outline-color: ${workspaceTheme.color.cyan};
    outline-offset: 3px;
  }

  body[data-caresync-theme='workspace'] input,
  body[data-caresync-theme='workspace'] select,
  body[data-caresync-theme='workspace'] textarea {
    color-scheme: dark;
  }

  button, input, select, textarea { font: inherit; }
  button, a { -webkit-tap-highlight-color: transparent; }
  button { color: inherit; }
  a { color: inherit; text-decoration: none; }
  img, svg { display: block; }

  ::selection { color: #070914; background: ${({ theme }) => theme.color.cyan}; }

  :focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: 3px;
  }

  html[data-caresync-motion='paused'] *,
  html[data-caresync-motion='paused'] *::before,
  html[data-caresync-motion='paused'] *::after {
    animation-play-state: paused !important;
  }

  html[data-caresync-motion='reduced'],
  html[data-caresync-motion='reduced'] *,
  html[data-caresync-motion='reduced'] *::before,
  html[data-caresync-motion='reduced'] *::after,
  html[data-caresync-motion='off'],
  html[data-caresync-motion='off'] *,
  html[data-caresync-motion='off'] *::before,
  html[data-caresync-motion='off'] *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }

  @media (prefers-reduced-motion: reduce) {
    html:not([data-caresync-motion]),
    html:not([data-caresync-motion]) *,
    html:not([data-caresync-motion]) *::before,
    html:not([data-caresync-motion]) *::after {
      scroll-behavior: auto !important;
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
    }
  }
`;
