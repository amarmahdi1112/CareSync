import styled, { css } from 'styled-components';

export const GlassPanel = styled.div<{ $interactive?: boolean; $accent?: 'plasma' | 'cyan' | 'amber' }>`
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: ${({ theme }) => theme.mode === 'workspace' ? '16px 7px 16px 7px' : theme.radius.lg};
  background:
    ${({ theme }) => theme.effect.panelHighlight},
    ${({ theme }) => theme.color.surface};
  box-shadow: ${({ theme }) => theme.shadow.panel};
  backdrop-filter: blur(${({ theme }) => theme.effect.panelBlur}) saturate(${({ theme }) => theme.effect.panelSaturation});

  &::after {
    position: absolute;
    inset: 0;
    content: '';
    pointer-events: none;
    border-radius: inherit;
    opacity: ${({ theme }) => theme.effect.panelSheenOpacity};
    background: ${({ theme }) => theme.effect.panelSheen};
  }

  ${({ $accent }) => $accent && css`
    &::before {
      position: absolute;
      top: 0;
      left: 22px;
      width: 84px;
      height: 1px;
      content: '';
      background: ${({ theme }) => $accent === 'cyan' ? theme.color.cyan : $accent === 'amber' ? theme.color.amber : theme.color.plasma};
      box-shadow: 0 0 ${({ theme }) => theme.effect.accentGlow} ${({ theme }) => $accent === 'cyan' ? theme.color.cyan : $accent === 'amber' ? theme.color.amber : theme.color.plasma};
    }
  `}

  ${({ $interactive, theme }) => $interactive && css`
    transition: transform ${theme.motion.normal} ${theme.motion.ease}, border-color ${theme.motion.normal} ease, background ${theme.motion.normal} ease;
    &:hover { transform: translateY(${theme.mode === 'workspace' ? '-1px' : '-3px'}); border-color: ${theme.color.borderStrong}; background-color: ${theme.color.surfaceHover}; }
  `}
`;

export const Eyebrow = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: ${({ theme }) => theme.color.cyan};
  font-size: ${({ theme }) => theme.mode === 'workspace' ? '.75rem' : '.69rem'};
  font-weight: ${({ theme }) => theme.mode === 'workspace' ? 600 : 750};
  letter-spacing: ${({ theme }) => theme.mode === 'workspace' ? '.08em' : '.16em'};
  line-height: 1;
  text-transform: uppercase;
`;

export const StatusChip = styled.span<{ $tone?: 'success' | 'warning' | 'info' | 'neutral' }>`
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: ${({ theme }) => theme.mode === 'workspace' ? '30px' : '28px'};
  padding: 5px 10px;
  border: 1px solid ${({ $tone, theme }) => theme.mode === 'workspace'
    ? $tone === 'success' ? 'rgba(142,216,176,.38)'
      : $tone === 'warning' ? 'rgba(242,190,116,.38)'
        : $tone === 'info' ? 'rgba(123,211,240,.38)' : theme.color.borderStrong
    : $tone === 'success' ? 'rgba(99,244,190,.28)'
      : $tone === 'warning' ? 'rgba(255,202,114,.28)'
        : $tone === 'info' ? 'rgba(83,230,255,.28)' : theme.color.border};
  border-radius: ${({ theme }) => theme.mode === 'workspace' ? '10px 4px 10px 4px' : theme.radius.pill};
  color: ${({ $tone, theme }) =>
    $tone === 'success' ? theme.color.mint :
    $tone === 'warning' ? theme.color.amber :
    $tone === 'info' ? theme.color.cyan : theme.color.textSoft};
  background: ${({ $tone, theme }) => theme.mode === 'workspace'
    ? $tone === 'success' ? 'rgba(142,216,176,.10)'
      : $tone === 'warning' ? 'rgba(242,190,116,.10)'
        : $tone === 'info' ? 'rgba(123,211,240,.10)' : 'rgba(168,177,190,.08)'
    : 'rgba(255,255,255,.025)'};
  font-size: ${({ theme }) => theme.mode === 'workspace' ? '.75rem' : '.7rem'};
  font-weight: ${({ theme }) => theme.mode === 'workspace' ? 600 : 700};
  letter-spacing: .04em;

  &::before {
    width: 6px;
    height: 6px;
    content: '';
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 ${({ theme }) => theme.effect.statusGlow} currentColor;
  }
`;

export const ActionButton = styled.button<{ $variant?: 'primary' | 'quiet' | 'danger' }>`
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: ${({ theme }) => theme.mode === 'workspace' ? '44px' : '42px'};
  padding: 0 15px;
  border: 1px solid ${({ $variant, theme }) =>
    $variant === 'primary' ? (theme.mode === 'workspace' ? theme.color.plasmaBright : 'rgba(198,168,255,.48)') :
    $variant === 'danger' ? (theme.mode === 'workspace' ? theme.color.coral : 'rgba(255,125,144,.35)') :
    theme.mode === 'workspace' ? theme.color.controlBorder : theme.color.border};
  border-radius: ${({ theme }) => theme.mode === 'workspace' ? '11px 5px 11px 5px' : theme.radius.md};
  color: ${({ $variant, theme }) => $variant === 'primary' && theme.mode === 'workspace'
    ? theme.color.ink
    : $variant === 'danger' ? theme.color.coral : theme.color.text};
  background: ${({ $variant, theme }) =>
    $variant === 'primary'
      ? theme.effect.primaryGradient
      : $variant === 'danger'
        ? theme.mode === 'workspace' ? 'rgba(238,145,135,.10)' : 'rgba(255,125,144,.08)'
        : theme.mode === 'workspace' ? theme.color.control : 'rgba(255,255,255,.035)'};
  box-shadow: ${({ $variant, theme }) => $variant === 'primary' ? theme.effect.primaryShadow : 'none'};
  cursor: pointer;
  font-size: .83rem;
  font-weight: ${({ theme }) => theme.mode === 'workspace' ? 600 : 720};
  transition: transform ${({ theme }) => theme.motion.fast} ease, border-color ${({ theme }) => theme.motion.fast} ease, filter ${({ theme }) => theme.motion.fast} ease;

  &:hover {
    transform: translateY(-1px);
    border-color: ${({ $variant, theme }) => theme.mode === 'workspace'
      ? $variant === 'danger' ? theme.color.coral : $variant === 'primary' ? theme.color.plasmaBright : theme.color.cyan
      : theme.color.plasmaBright};
    filter: brightness(${({ theme }) => theme.mode === 'workspace' ? '1.02' : '1.08'});
  }
  &:active { transform: translateY(0); }
  &:disabled { cursor: not-allowed; opacity: .5; transform: none; }
  svg { width: 18px; height: 18px; }
`;

export const IconButton = styled.button`
  display: inline-grid;
  width: ${({ theme }) => theme.mode === 'workspace' ? '44px' : '42px'};
  height: ${({ theme }) => theme.mode === 'workspace' ? '44px' : '42px'};
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.mode === 'workspace' ? theme.color.controlBorder : theme.color.border};
  border-radius: ${({ theme }) => theme.mode === 'workspace' ? '11px 5px 11px 5px' : theme.radius.md};
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.mode === 'workspace' ? theme.color.control : 'rgba(255,255,255,.025)'};
  cursor: pointer;
  transition: color ${({ theme }) => theme.motion.fast} ease, border-color ${({ theme }) => theme.motion.fast} ease, background ${({ theme }) => theme.motion.fast} ease;

  &:hover { color: ${({ theme }) => theme.color.text}; border-color: ${({ theme }) => theme.color.borderStrong}; background: ${({ theme }) => theme.mode === 'workspace' ? theme.color.surfaceHover : 'rgba(255,255,255,.055)'}; }
  svg { width: 19px; height: 19px; }
`;
