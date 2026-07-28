import styled, { keyframes } from 'styled-components';
import { GlassPanel } from '../../components/ui/Primitives';

const arrive = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
`;

const breathe = keyframes`
  0%, 100% { opacity: .45; }
  50% { opacity: 1; }
`;

export const OperationPage = styled.div`
  display: grid;
  gap: 18px;
  min-width: 0;
`;

export const OperationHeader = styled.header`
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 22px;

  h1 {
    margin: 9px 0 6px;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(1.65rem, 3.5vw, 2.5rem);
    font-weight: 530;
    letter-spacing: -.055em;
  }

  p {
    max-width: 760px;
    margin: 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .79rem;
    line-height: 1.65;
  }

  @media (max-width: 760px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;

export const PrivateMark = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: max-content;
  padding: 9px 12px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px 5px 12px 5px;
  color: ${({ theme }) => theme.color.textSoft};
  background: ${({ theme }) => theme.color.surface};
  font-size: .7rem;

  i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: ${({ theme }) => theme.color.mint};
    box-shadow: 0 0 8px ${({ theme }) => theme.color.mint};
    animation: ${breathe} 2s ease-in-out infinite;
  }

  @media (prefers-reduced-motion: reduce) { i { animation: none; } }
`;

export const ScopePanel = styled(GlassPanel)<{ $columns?: number }>`
  display: grid;
  grid-template-columns: repeat(${({ $columns = 3 }) => $columns}, minmax(150px, 1fr)) auto;
  align-items: end;
  gap: 11px;
  padding: 14px;

  @media (max-width: 960px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 560px) { grid-template-columns: 1fr; }
`;

export const OperationField = styled.label<{ $wide?: boolean }>`
  display: grid;
  grid-column: ${({ $wide }) => $wide ? '1 / -1' : 'auto'};
  gap: 6px;
  min-width: 0;

  > span {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .65rem;
    font-weight: 650;
    letter-spacing: .07em;
    text-transform: uppercase;
  }

  input,
  select,
  textarea {
    width: 100%;
    min-height: 44px;
    padding: 0 11px;
    border: 1px solid ${({ theme }) => theme.color.controlBorder};
    border-radius: 11px 5px 11px 5px;
    outline: 0;
    color: ${({ theme }) => theme.color.text};
    background: ${({ theme }) => theme.color.control};
    font: inherit;
    font-size: .76rem;
  }

  textarea {
    min-height: 100px;
    padding-top: 11px;
    resize: vertical;
  }

  input:focus,
  select:focus,
  textarea:focus {
    border-color: ${({ theme }) => theme.color.cyan};
    box-shadow: 0 0 0 3px color-mix(in srgb, ${({ theme }) => theme.color.cyan} 15%, transparent);
  }

  input:disabled,
  select:disabled,
  textarea:disabled { cursor: not-allowed; opacity: .7; }

  small {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .66rem;
    line-height: 1.5;
  }
`;

export const MetricGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;

  @media (max-width: 960px) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

export const MetricCard = styled(GlassPanel)`
  padding: 13px 14px;
  animation: ${arrive} 260ms ease both;

  span {
    display: flex;
    align-items: center;
    gap: 7px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: .67rem;
  }

  svg { width: 16px; color: ${({ theme }) => theme.color.cyan}; }
  strong { display: block; margin-top: 8px; font-family: 'CareSync Display', sans-serif; font-size: 1.5rem; font-weight: 540; }

  @media (prefers-reduced-motion: reduce) { animation: none; }
`;

export const Toolbar = styled(GlassPanel)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;

  @media (max-width: 760px) { align-items: stretch; flex-direction: column; }
`;

export const SearchField = styled.label`
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: min(360px, 100%);
  min-height: 44px;
  padding: 0 11px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 11px 5px 11px 5px;
  background: ${({ theme }) => theme.color.control};

  svg { width: 18px; color: ${({ theme }) => theme.color.textMuted}; }
  input { width: 100%; min-height: 44px; border: 0; outline: 0; color: ${({ theme }) => theme.color.text}; background: transparent; font: inherit; font-size: .75rem; }
`;

export const FilterRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
`;

export const FilterButton = styled.button<{ $active?: boolean }>`
  min-height: 44px;
  padding: 0 11px;
  border: 1px solid ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.controlBorder};
  border-radius: 10px 4px 10px 4px;
  color: ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textSoft};
  background: ${({ $active, theme }) => $active ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.cyan})` : theme.color.control};
  cursor: pointer;
  font: inherit;
  font-size: .68rem;
  font-weight: 600;
`;

export const OperationNotice = styled(GlassPanel)<{ $error?: boolean; $warning?: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border-color: ${({ $error, $warning, theme }) => $error ? theme.color.coral : $warning ? theme.color.amber : theme.color.border};
  color: ${({ $error, $warning, theme }) => $error ? theme.color.coral : $warning ? theme.color.amber : theme.color.textSoft};
  font-size: .75rem;
  line-height: 1.55;

  svg { width: 19px; flex: 0 0 auto; }

  button {
    min-width: 44px;
    min-height: 44px;
    margin-left: 6px;
    padding: 0 11px;
    border: 1px solid currentColor;
    border-radius: 9px 4px 9px 4px;
    color: inherit;
    background: transparent;
    cursor: pointer;
    font: inherit;
    font-weight: 650;
  }
`;

export const CardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;

  @media (max-width: 1060px) { grid-template-columns: 1fr; }
`;

export const OperationCard = styled(GlassPanel)`
  display: grid;
  align-content: start;
  gap: 13px;
  padding: 15px;
  animation: ${arrive} 260ms ease both;

  @media (prefers-reduced-motion: reduce) { animation: none; }
`;

export const CardHeader = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

  h2 { margin: 0; font-size: .91rem; font-weight: 610; }
  p { margin: 4px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; line-height: 1.5; }

  @media (max-width: 460px) { flex-direction: column; }
`;

export const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

export const DetailGrid = styled.dl`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;

  > div {
    min-width: 0;
    padding: 10px 11px;
    border: 1px solid ${({ theme }) => theme.color.border};
    border-radius: 11px 5px 11px 5px;
    background: ${({ theme }) => theme.color.surfaceStrong};
  }

  dt { color: ${({ theme }) => theme.color.textMuted}; font-size: .63rem; font-weight: 650; letter-spacing: .055em; text-transform: uppercase; }
  dd { margin: 5px 0 0; color: ${({ theme }) => theme.color.textSoft}; font-size: .73rem; line-height: 1.5; overflow-wrap: anywhere; }

  @media (max-width: 520px) { grid-template-columns: 1fr; }
`;

export const EmptyState = styled(GlassPanel)`
  display: grid;
  min-height: 240px;
  place-items: center;
  padding: 30px;
  text-align: center;

  svg { width: 38px; margin: 0 auto 10px; color: ${({ theme }) => theme.color.textMuted}; }
  h2 { margin: 0 0 6px; font-size: 1rem; }
  p { max-width: 540px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .73rem; line-height: 1.6; }
`;
