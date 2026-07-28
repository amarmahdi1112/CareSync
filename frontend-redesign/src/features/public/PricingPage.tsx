import { ArrowRightIcon, CheckCircleIcon, InformationCircleIcon, SparklesIcon } from '@heroicons/react/24/outline';
import styled from 'styled-components';
import {
  ContentWidth, PrimaryCta, PublicLayout, PublicSection, SecondaryCta, SectionKicker,
} from '../../components/public/PublicLayout';
import { CenterKicker, CtaBand, InteriorHero, TruthNote } from './publicPageStyles';
import { GlassPanel, StatusChip } from '../../components/ui/Primitives';

const PricingGrid = styled.div`
  display: grid;
  max-width: 920px;
  grid-template-columns: 1.12fr .88fr;
  gap: 14px;
  margin: 0 auto;
  @media (max-width: 740px) { grid-template-columns: 1fr; }
`;

const PriceCard = styled(GlassPanel)<{ $featured?: boolean }>`
  padding: clamp(26px, 5vw, 44px);
  background: ${({ $featured }) => $featured ? 'linear-gradient(145deg, rgba(169,120,255,.13), rgba(15,20,39,.88))' : undefined};
  header { display: flex; justify-content: space-between; align-items: start; gap: 14px; }
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 1.35rem; letter-spacing: -.05em; }
  header p { margin: 6px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; }
  ul { display: grid; gap: 12px; margin: 28px 0 0; padding: 0; list-style: none; }
  li { display: grid; grid-template-columns: 18px 1fr; gap: 9px; color: ${({ theme }) => theme.color.textSoft}; font-size: .7rem; line-height: 1.55; }
  li svg { width: 17px; color: ${({ theme }) => theme.color.mint}; }
`;

const Price = styled.div`
  display: flex;
  align-items: end;
  gap: 7px;
  margin-top: 30px;
  strong { font-family: 'CareSync Display', sans-serif; font-size: clamp(2.2rem, 5vw, 3.8rem); font-weight: 520; letter-spacing: -.08em; line-height: 1; }
  span { padding-bottom: 7px; color: ${({ theme }) => theme.color.textMuted}; font-size: .66rem; }
`;

const CardAction = styled(PrimaryCta)`width: 100%; margin-top: 30px;`;

export default function PricingPage() {
  return <PublicLayout>
    <InteriorHero><ContentWidth><CenterKicker><SectionKicker><SparklesIcon /> Straightforward foundation scope</SectionKicker></CenterKicker><h1>Pricing follows a verified product.</h1><p>CareSync Basic is one focused product for the first facility. Subscription checkout and commercial billing are deliberately deferred while the complete operating path is built and verified.</p></ContentWidth></InteriorHero>
    <PublicSection><ContentWidth>
      <PricingGrid>
        <PriceCard $featured $accent="plasma"><header><div><h2>CareSync Basic</h2><p>For the first licensed childcare facility</p></div><StatusChip $tone="info">Foundation access</StatusChip></header><Price><strong>Basic first</strong><span>price published before billing</span></Price><ul>
          <li><CheckCircleIcon /> Owner registration and guided facility setup</li>
          <li><CheckCircleIcon /> Daycare/OSC programs and unlimited room setup for the registered facility</li>
          <li><CheckCircleIcon /> Families, guardians, emergency contacts, and profile context</li>
          <li><CheckCircleIcon /> Children, health facts, and enrollment</li>
          <li><CheckCircleIcon /> Actual check-in, check-out, no-show, and history</li>
          <li><CheckCircleIcon /> Organization, profile, and password settings</li>
        </ul><CardAction to="/register">Create your workspace <ArrowRightIcon /></CardAction></PriceCard>
        <PriceCard $accent="cyan"><header><div><h2>The scope promise</h2><p>CareSync Basic stays intentionally focused</p></div></header><ul>
          <li><InformationCircleIcon /> Configure every operating room during guided setup—no room-count limit in current Basic</li>
          <li><InformationCircleIcon /> Only real Basic records appear in the workspace</li>
          <li><InformationCircleIcon /> Every protected request resolves through organization ownership</li>
          <li><InformationCircleIcon /> Attendance captures real check-in, check-out, and no-show history</li>
          <li><InformationCircleIcon /> Commercial billing remains inactive until the product path is verified</li>
        </ul><TruthNote><InformationCircleIcon /><span>No payment is collected by CareSync Basic at this stage. If future plans introduce entitlements, their price and limits will be shown before subscriptions are activated—never hidden inside onboarding.</span></TruthNote></PriceCard>
      </PricingGrid>
    </ContentWidth></PublicSection>
    <PublicSection><ContentWidth><CtaBand $accent="cyan"><div><SectionKicker><CheckCircleIcon /> Honest scope</SectionKicker><h2>Start with the operating record.</h2><p>Advanced modules will return only when they have their own tested product boundary. Basic stays focused on the daily records a daycare needs first.</p></div><div><PrimaryCta to="/register">Create account <ArrowRightIcon /></PrimaryCta><SecondaryCta to="/product">Review Basic</SecondaryCta></div></CtaBand></ContentWidth></PublicSection>
  </PublicLayout>;
}
