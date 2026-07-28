import styled from 'styled-components';
import { GlassPanel } from '../../components/ui/Primitives';

export const InteriorHero = styled.section`
  position: relative;
  padding: clamp(76px, 11vw, 132px) 0 clamp(54px, 8vw, 86px);
  text-align: center;
  &::before {
    position: absolute;
    top: -220px;
    left: 50%;
    z-index: -1;
    width: min(900px, 100vw);
    height: 600px;
    content: '';
    background: radial-gradient(circle, rgba(169,120,255,.16), transparent 68%);
    transform: translateX(-50%);
  }
  h1 { max-width: 900px; margin: 17px auto 18px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2.8rem, 7vw, 6rem); font-weight: 500; letter-spacing: -.085em; line-height: .96; }
  > div > p { max-width: 710px; margin: 0 auto; color: ${({ theme }) => theme.color.textMuted}; font-size: clamp(.8rem, 1.5vw, .96rem); line-height: 1.82; }
`;

export const CenterKicker = styled.div`
  display: flex;
  justify-content: center;
`;

export const InfoGrid = styled.div<{ $columns?: number }>`
  display: grid;
  grid-template-columns: repeat(${({ $columns = 3 }) => $columns}, minmax(0, 1fr));
  gap: 13px;
  margin-top: 34px;
  @media (max-width: 900px) { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: 560px) { grid-template-columns: 1fr; }
`;

export const InfoCard = styled(GlassPanel)`
  padding: clamp(22px, 3vw, 30px);
  svg { width: 27px; color: ${({ theme }) => theme.color.cyan}; }
  h2, h3 { margin: 24px 0 9px; font-family: 'CareSync Display', sans-serif; font-size: 1.05rem; letter-spacing: -.04em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; line-height: 1.75; }
  ul { display: grid; gap: 9px; margin: 18px 0 0; padding: 0; list-style: none; }
  li { position: relative; padding-left: 19px; color: ${({ theme }) => theme.color.textSoft}; font-size: .67rem; line-height: 1.6; }
  li::before { position: absolute; top: .58em; left: 0; width: 7px; height: 7px; content: ''; border-radius: 50%; background: ${({ theme }) => theme.color.mint}; box-shadow: 0 0 10px rgba(99,244,190,.55); }
`;

export const Split = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  align-items: center;
  gap: clamp(40px, 8vw, 100px);
  @media (max-width: 800px) { grid-template-columns: 1fr; }
`;

export const FeatureStack = styled.div`
  display: grid;
  gap: 10px;
`;

export const FeatureRow = styled(GlassPanel)`
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 15px;
  padding: 18px;
  > svg { width: 22px; margin: 8px auto 0; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 0 0 5px; font-size: .78rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; line-height: 1.65; }
`;

export const CtaBand = styled(GlassPanel)`
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 34px;
  padding: clamp(28px, 6vw, 58px);
  background: linear-gradient(125deg, rgba(169,120,255,.13), rgba(83,230,255,.055));
  h2 { margin: 12px 0 10px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 4vw, 3.2rem); font-weight: 520; letter-spacing: -.06em; }
  p { max-width: 650px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; line-height: 1.75; }
  > div:last-child { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }
  @media (max-width: 760px) { grid-template-columns: 1fr; > div:last-child { justify-content: flex-start; } }
  @media (max-width: 460px) { > div:last-child a { width: 100%; } }
`;

export const TruthNote = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 24px;
  padding: 14px 16px;
  border: 1px solid rgba(83,230,255,.18);
  border-radius: 13px;
  color: ${({ theme }) => theme.color.textMuted};
  background: rgba(83,230,255,.035);
  font-size: .66rem;
  line-height: 1.65;
  svg { width: 18px; flex: 0 0 auto; color: ${({ theme }) => theme.color.cyan}; }
`;
