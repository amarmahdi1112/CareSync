import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { ArrowLeftIcon, SignalSlashIcon } from '@heroicons/react/24/outline';
import { ActionButton, Eyebrow, GlassPanel } from '../../components/ui/Primitives';

const Wrap = styled(GlassPanel)`
  display: grid;
  min-height: calc(100vh - 190px);
  place-items: center;
  padding: 30px;
  text-align: center;
  svg { width: 48px; margin: 0 auto 18px; color: ${({ theme }) => theme.color.plasmaBright}; }
  h1 { margin: 12px 0 8px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2.5rem, 8vw, 6rem); font-weight: 500; letter-spacing: -.08em; }
  p { max-width: 460px; margin: 0 auto 24px; color: ${({ theme }) => theme.color.textMuted}; }
`;

export default function NotFoundPage() {
  const navigate = useNavigate();
  return <Wrap $accent="plasma"><div><SignalSlashIcon /><Eyebrow>Signal not found</Eyebrow><h1>Off the map.</h1><p>This route is outside the CareSync command network.</p><ActionButton $variant="primary" onClick={() => navigate('/dashboard')}><ArrowLeftIcon /> Return to command deck</ActionButton></div></Wrap>;
}
