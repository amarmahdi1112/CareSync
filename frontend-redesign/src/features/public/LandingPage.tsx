import {
  ArrowRightIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  ClipboardDocumentCheckIcon,
  ClockIcon,
  HomeModernIcon,
  IdentificationIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import {
  ContentWidth,
  PrimaryCta,
  PublicLayout,
  PublicSection,
  SecondaryCta,
  SectionKicker,
  SectionLead,
  SectionTitle,
} from '../../components/public/PublicLayout';
import { GlassPanel, StatusChip } from '../../components/ui/Primitives';

const drift = keyframes`50% { transform: translate3d(0,-8px,0); }`;

const Hero = styled.section`
  position: relative;
  padding: clamp(74px, 10vw, 132px) 0 clamp(64px, 9vw, 108px);
  &::before {
    position: absolute;
    top: -220px;
    left: 50%;
    z-index: -1;
    width: 860px;
    height: 680px;
    content: '';
    border-radius: 50%;
    background: radial-gradient(circle, rgba(169,120,255,.17), rgba(83,230,255,.055) 40%, transparent 70%);
    transform: translateX(-50%);
    pointer-events: none;
  }
`;

const HeroGrid = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(390px, .92fr);
  align-items: center;
  gap: clamp(42px, 7vw, 90px);
  @media (max-width: 920px) { grid-template-columns: 1fr; }
`;

const HeroCopy = styled.div`
  h1 {
    max-width: 820px;
    margin: 18px 0 22px;
    font-family: 'CareSync Display', sans-serif;
    font-size: clamp(3rem, 7.2vw, 6.6rem);
    font-weight: 490;
    letter-spacing: -.09em;
    line-height: .93;
  }
  h1 span { color: ${({ theme }) => theme.color.cyan}; text-shadow: 0 0 32px rgba(83,230,255,.22); }
  > p { max-width: 680px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: clamp(.84rem, 1.4vw, 1rem); line-height: 1.82; }
`;

const HeroActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 11px;
  margin-top: 30px;
  @media (max-width: 480px) { > a { width: 100%; } }
`;

const Assurance = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 10px 20px;
  margin-top: 24px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .65rem;
  span { display: inline-flex; align-items: center; gap: 7px; }
  svg { width: 15px; color: ${({ theme }) => theme.color.mint}; }
`;

const OrbitPanel = styled(GlassPanel)`
  min-height: 540px;
  padding: 22px;
  background:
    radial-gradient(circle at 50% 48%, rgba(169,120,255,.16), transparent 35%),
    linear-gradient(145deg, rgba(17,24,45,.9), rgba(8,11,24,.82));
  animation: ${drift} 7s ease-in-out infinite;
  @media (max-width: 920px) { min-height: 480px; }
  @media (max-width: 560px) { min-height: auto; animation: none; }
`;

const PanelTop = styled.div`
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  strong { font-family: 'CareSync Display', sans-serif; font-size: .82rem; }
`;

const SystemMap = styled.div`
  position: relative;
  height: 440px;
  margin-top: 14px;
  &::before, &::after {
    position: absolute;
    top: 50%;
    left: 50%;
    content: '';
    border: 1px solid rgba(169,120,255,.18);
    border-radius: 50%;
    transform: translate(-50%, -50%);
  }
  &::before { width: 310px; height: 310px; }
  &::after { width: 210px; height: 210px; border-style: dashed; border-color: rgba(83,230,255,.18); }
  @media (max-width: 560px) {
    display: grid;
    height: auto;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    padding-top: 20px;
    &::before, &::after { display: none; }
  }
`;

const Core = styled.div`
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  display: grid;
  width: 126px;
  height: 126px;
  place-items: center;
  padding: 18px;
  border: 1px solid rgba(198,168,255,.42);
  border-radius: 50%;
  text-align: center;
  background: rgba(13,18,34,.94);
  box-shadow: 0 0 45px rgba(169,120,255,.18);
  transform: translate(-50%,-50%);
  svg { width: 28px; color: ${({ theme }) => theme.color.plasmaBright}; }
  strong { display: block; margin-top: 5px; font-family: 'CareSync Display', sans-serif; font-size: .68rem; }
  @media (max-width: 560px) { position: static; width: auto; height: auto; grid-column: 1 / -1; border-radius: 15px; transform: none; }
`;

const Node = styled.div<{ $position: 'one' | 'two' | 'three' | 'four' }>`
  position: absolute;
  z-index: 3;
  display: grid;
  min-width: 142px;
  gap: 7px;
  padding: 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px;
  background: rgba(11,16,32,.93);
  box-shadow: 0 14px 35px rgba(0,0,0,.24);
  svg { width: 19px; color: ${({ theme }) => theme.color.cyan}; }
  strong { font-size: .7rem; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .56rem; }
  ${({ $position }) => $position === 'one' && 'top: 22px; left: 6%;'}
  ${({ $position }) => $position === 'two' && 'top: 58px; right: 3%;'}
  ${({ $position }) => $position === 'three' && 'bottom: 46px; left: 4%;'}
  ${({ $position }) => $position === 'four' && 'right: 4%; bottom: 24px;'}
  @media (max-width: 560px) { position: static; min-width: 0; }
`;

const FoundationGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 34px;
  @media (max-width: 960px) { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: 540px) { grid-template-columns: 1fr; }
`;

const FoundationCard = styled(GlassPanel)`
  padding: 23px;
  svg { width: 25px; color: ${({ theme }) => theme.color.cyan}; }
  h3 { margin: 24px 0 9px; font-family: 'CareSync Display', sans-serif; font-size: 1rem; letter-spacing: -.04em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .68rem; line-height: 1.72; }
`;

const Process = styled.div`
  display: grid;
  grid-template-columns: .82fr 1.18fr;
  align-items: start;
  gap: clamp(36px, 7vw, 92px);
  @media (max-width: 800px) { grid-template-columns: 1fr; }
`;

const Steps = styled.div`
  display: grid;
  gap: 10px;
`;

const Step = styled(GlassPanel)`
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 15px;
  padding: 18px;
  > span { display:grid; width:42px; height:42px; place-items:center; border:1px solid rgba(83,230,255,.25); border-radius:12px; color:${({ theme }) => theme.color.cyan}; font-size:.67rem; font-weight:800; background:rgba(83,230,255,.05); }
  h3 { margin: 1px 0 5px; font-size: .78rem; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .65rem; line-height: 1.65; }
`;

const TrustBand = styled(GlassPanel)`
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 40px;
  padding: clamp(28px, 6vw, 62px);
  background: linear-gradient(125deg, rgba(169,120,255,.12), rgba(83,230,255,.055));
  @media (max-width: 760px) { grid-template-columns: 1fr; }
`;

const TrustPoints = styled.div`
  display: grid;
  gap: 11px;
  span { display: flex; align-items: center; gap: 9px; color: ${({ theme }) => theme.color.textSoft}; font-size: .7rem; }
  svg { width: 18px; color: ${({ theme }) => theme.color.mint}; }
`;

export default function LandingPage() {
  return (
    <PublicLayout>
      <Hero>
        <ContentWidth><HeroGrid>
          <HeroCopy>
            <SectionKicker><SparklesIcon /> Alberta-first childcare operations</SectionKicker>
            <h1>Run the day with <span>clarity.</span></h1>
            <p>CareSync Basic gives daycare operators one dependable record for facilities, rooms, families, children, enrollment, and actual daily attendance—without hiding essential work behind complexity.</p>
            <HeroActions><PrimaryCta to="/register">Create your workspace <ArrowRightIcon /></PrimaryCta><SecondaryCta to="/product">Explore the foundation</SecondaryCta></HeroActions>
            <Assurance><span><ShieldCheckIcon /> Organization-scoped records</span><span><CheckCircleIcon /> Actual attendance as the source of truth</span></Assurance>
          </HeroCopy>
          <OrbitPanel $accent="plasma">
            <PanelTop><strong>Basic operating record</strong><StatusChip $tone="success">Clear by design</StatusChip></PanelTop>
            <SystemMap>
              <Core><BuildingOffice2Icon /><strong>Your daycare</strong></Core>
              <Node $position="one"><UserGroupIcon /><strong>Families</strong><span>Guardians, contacts, profile context</span></Node>
              <Node $position="two"><UsersIcon /><strong>Children</strong><span>Enrollment and health facts</span></Node>
              <Node $position="three"><HomeModernIcon /><strong>Rooms</strong><span>Programs and capacity</span></Node>
              <Node $position="four"><ClockIcon /><strong>Attendance</strong><span>Check-in, check-out, no-show</span></Node>
            </SystemMap>
          </OrbitPanel>
        </HeroGrid></ContentWidth>
      </Hero>

      <PublicSection><ContentWidth>
        <SectionKicker><IdentificationIcon /> The dependable foundation</SectionKicker>
        <SectionTitle>Every basic record belongs together.</SectionTitle>
        <SectionLead>CareSync starts where real daycare work starts: knowing who is enrolled, where they belong, who can pick them up, and whether they are safely present today.</SectionLead>
        <FoundationGrid>
          <FoundationCard $accent="plasma"><UserGroupIcon /><h3>Households in context</h3><p>Keep guardians, emergency contacts, legacy profile markers, and children connected to one clear family record.</p></FoundationCard>
          <FoundationCard $accent="cyan"><UsersIcon /><h3>Complete child profiles</h3><p>Record identity, health facts, enrollment status, and the facility and room providing care.</p></FoundationCard>
          <FoundationCard $accent="amber"><HomeModernIcon /><h3>Rooms that reflect reality</h3><p>Configure programs, age groups, room capacity, and active enrollments around each licensed location.</p></FoundationCard>
          <FoundationCard $accent="cyan"><ClipboardDocumentCheckIcon /><h3>Actual daily attendance</h3><p>Capture check-in, check-out, no-shows, corrections, and history as operating evidence—not a generated plan.</p></FoundationCard>
        </FoundationGrid>
      </ContentWidth></PublicSection>

      <PublicSection><ContentWidth><Process>
        <div><SectionKicker><SparklesIcon /> A guided beginning</SectionKicker><SectionTitle>From account to first check-out.</SectionTitle><SectionLead>The Basic journey is intentionally linear, resumable, and honest. Each step establishes information the next one truly needs.</SectionLead></div>
        <Steps>
          <Step $accent="plasma"><span>01</span><div><h3>Create the owner workspace</h3><p>Register the person responsible for the daycare and establish its organization boundary.</p></div></Step>
          <Step $accent="cyan"><span>02</span><div><h3>Describe the first facility</h3><p>Add licensed location details, operating programs, and the rooms where care happens.</p></div></Step>
          <Step $accent="plasma"><span>03</span><div><h3>Register a family and child</h3><p>Capture contacts, profile context, enrollment, health facts, and the assigned care room.</p></div></Step>
          <Step $accent="cyan"><span>04</span><div><h3>Record the real day</h3><p>Check the child in, check them out, and retain a clear, auditable attendance history.</p></div></Step>
        </Steps>
      </Process></ContentWidth></PublicSection>

      <PublicSection><ContentWidth><TrustBand $accent="cyan">
        <div><SectionKicker><ShieldCheckIcon /> Trust is part of the workflow</SectionKicker><SectionTitle>Boundaries before features.</SectionTitle><SectionLead>CareSync Basic is being built around explicit organization ownership, fail-closed access, traceable corrections, and actual attendance as an independent operating record.</SectionLead><HeroActions><PrimaryCta to="/register">Begin organization setup <ArrowRightIcon /></PrimaryCta><SecondaryCta to="/security">Read the security approach</SecondaryCta></HeroActions></div>
        <TrustPoints><span><CheckCircleIcon /> One active organization context</span><span><CheckCircleIcon /> Facility-owned room and attendance records</span><span><CheckCircleIcon /> Mutation history instead of silent overwrites</span><span><CheckCircleIcon /> Advanced modules stay hidden until ready</span></TrustPoints>
      </TrustBand></ContentWidth></PublicSection>
    </PublicLayout>
  );
}
