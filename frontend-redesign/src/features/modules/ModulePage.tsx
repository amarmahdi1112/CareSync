import { useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  BeakerIcon,
  CheckCircleIcon,
  CubeTransparentIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { DEFERRED_MODULE_COPY } from '../../config/activeRuntimeCopy';
import { findNavigationItem } from '../../data/navigation';

const enter = keyframes`from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); }`;

const Page = styled.div`
  display: grid;
  min-height: calc(100vh - 164px);
  align-content: center;
  gap: 18px;
  animation: ${enter} 380ms ${({ theme }) => theme.motion.ease} both;
`;

const Hero = styled(GlassPanel)`
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(300px, .72fr);
  padding: clamp(24px, 5vw, 62px);
  background:
    radial-gradient(circle at 78% 33%, rgba(83,230,255,.09), transparent 25%),
    radial-gradient(circle at 84% 10%, rgba(169,120,255,.16), transparent 34%),
    ${({ theme }) => theme.color.surface};
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const Copy = styled.div`
  position: relative;
  z-index: 1;
  h1 { margin: 14px 0 13px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2.1rem, 5.4vw, 5.4rem); font-weight: 500; letter-spacing: -.075em; line-height: .96; }
  > p { max-width: 650px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .88rem; line-height: 1.8; }
`;

const Actions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 25px;
`;

const Visual = styled.div`
  position: relative;
  display: grid;
  min-height: 320px;
  place-items: center;
  @media (max-width: 760px) { min-height: 260px; }
`;

const Cube = styled.div`
  position: relative;
  display: grid;
  width: 190px;
  height: 190px;
  place-items: center;
  border: 1px solid rgba(169,120,255,.3);
  border-radius: 44px;
  background: linear-gradient(145deg, rgba(169,120,255,.13), rgba(83,230,255,.035));
  box-shadow: inset 0 0 40px rgba(169,120,255,.09), 0 0 50px rgba(83,230,255,.06);
  transform: rotate(9deg);
  &::before { position: absolute; inset: 19px; content: ''; border: 1px dashed rgba(83,230,255,.27); border-radius: 33px; }
  svg { width: 68px; color: ${({ theme }) => theme.color.plasmaBright}; filter: drop-shadow(0 0 18px rgba(169,120,255,.42)); transform: rotate(-9deg); }
`;

const Badge = styled.div<{ $position: 'top' | 'bottom' }>`
  position: absolute;
  ${({ $position }) => $position === 'top' ? 'top: 15%; right: 3%;' : 'bottom: 13%; left: 2%;'}
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 11px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 11px;
  background: rgba(10,14,28,.86);
  box-shadow: ${({ theme }) => theme.shadow.panel};
  font-size: .64rem;
  svg { width: 16px; color: ${({ theme }) => theme.color.cyan}; }
`;

const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 13px;
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const Card = styled(GlassPanel)`
  padding: 18px;
  svg { width: 22px; margin-bottom: 18px; color: ${({ theme }) => theme.color.plasmaBright}; }
  h2 { margin: 0 0 5px; font-size: .82rem; font-weight: 680; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .67rem; line-height: 1.6; }
`;

export default function ModulePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const item = findNavigationItem(location.pathname);
  const title = item?.label || 'Module';

  return (
    <Page>
      <Hero $accent="plasma">
        <Copy>
          <Eyebrow><BeakerIcon width={14} /> Redesign migration lane</Eyebrow>
          <h1>{title}.</h1>
          <p>{DEFERRED_MODULE_COPY}</p>
          <Actions>
            <ActionButton $variant="primary" onClick={() => navigate('/dashboard')}><ArrowLeftIcon /> Return to command deck</ActionButton>
            <StatusChip $tone={item?.status === 'migrating' ? 'info' : 'warning'}>{item?.status === 'migrating' ? 'Migration designed' : 'Queued after core'}</StatusChip>
          </Actions>
        </Copy>
        <Visual aria-hidden="true">
          <Cube><CubeTransparentIcon /></Cube>
          <Badge $position="top"><SparklesIcon /> Original futuristic system</Badge>
          <Badge $position="bottom"><ShieldCheckIcon /> Legacy remains untouched</Badge>
        </Visual>
      </Hero>
      <Cards>
        <Card $accent="cyan"><CheckCircleIcon /><h2>Behavior first</h2><p>Existing business rules and data safety gates are inventoried before a workflow moves here.</p></Card>
        <Card $accent="plasma"><CubeTransparentIcon /><h2>Feature-owned design</h2><p>Each domain receives typed adapters, focused components, and its own migration tests.</p></Card>
        <Card $accent="amber"><ShieldCheckIcon /><h2>Explicit release gates</h2><p>The old route retires only after parity, data validation, and responsive QA all pass.</p></Card>
      </Cards>
    </Page>
  );
}
