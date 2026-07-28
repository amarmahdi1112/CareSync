import {
  ArrowRightIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  ClipboardDocumentCheckIcon,
  HeartIcon,
  HomeModernIcon,
  IdentificationIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import {
  ContentWidth, PrimaryCta, PublicLayout, PublicSection, SecondaryCta,
  SectionKicker, SectionLead, SectionTitle,
} from '../../components/public/PublicLayout';
import { CenterKicker, CtaBand, FeatureRow, FeatureStack, InfoCard, InfoGrid, InteriorHero, Split, TruthNote } from './publicPageStyles';

export default function ProductPage() {
  return <PublicLayout>
    <InteriorHero><ContentWidth><CenterKicker><SectionKicker><IdentificationIcon /> CareSync Basic</SectionKicker></CenterKicker><h1>The operating record a daycare can trust.</h1><p>CareSync Basic focuses on the records required to open the day, care for children safely, and close it with a complete attendance history. Advanced automation remains outside this foundation.</p></ContentWidth></InteriorHero>

    <PublicSection><ContentWidth>
      <SectionKicker><BuildingOffice2Icon /> One connected foundation</SectionKicker><SectionTitle>Built around how care is actually organized.</SectionTitle><SectionLead>An organization owns licensed facilities. Facilities contain programs and rooms. Families connect guardians and children. Enrollment connects each child to care, and attendance records what truly happened.</SectionLead>
      <InfoGrid>
        <InfoCard $accent="plasma"><BuildingOffice2Icon /><h2>Organization and facility</h2><p>Establish the licensed operating identity, first location, programs, rooms, hours, and capacity before child records enter the workspace.</p></InfoCard>
        <InfoCard $accent="cyan"><UserGroupIcon /><h2>Family record</h2><p>Keep guardians, emergency contacts, legacy profile markers, and children connected without duplicating household context. Verified authority remains separate from the profile.</p></InfoCard>
        <InfoCard $accent="amber"><UsersIcon /><h2>Child and enrollment</h2><p>Record identity, health facts, status, care location, program, room, and the dates that define an active enrollment.</p></InfoCard>
      </InfoGrid>
    </ContentWidth></PublicSection>

    <PublicSection><ContentWidth><Split>
      <div><SectionKicker><ClipboardDocumentCheckIcon /> Actual attendance</SectionKicker><SectionTitle>A history of the real day.</SectionTitle><SectionLead>Attendance is a source-of-truth operating record and never borrows planned or synthetic values. Each child-day contains the real service date, any no-show state, and one or more check-in/check-out intervals.</SectionLead><TruthNote><ShieldCheckIcon /><span>Corrections retain actor, reason, and before/after state. An open interval cannot overlap another open interval for the same child.</span></TruthNote></div>
      <FeatureStack>
        <FeatureRow $accent="cyan"><CheckCircleIcon /><div><h3>Check in with context</h3><p>Choose the enrolled child, facility, room, and exact arrival time.</p></div></FeatureRow>
        <FeatureRow $accent="plasma"><HomeModernIcon /><div><h3>Keep room placement visible</h3><p>Daily attendance remains connected to the location and room responsible for care.</p></div></FeatureRow>
        <FeatureRow $accent="cyan"><ClipboardDocumentCheckIcon /><div><h3>Complete the interval</h3><p>Check-out validates time order and produces a finished operating record.</p></div></FeatureRow>
        <FeatureRow $accent="amber"><HeartIcon /><div><h3>Record a no-show honestly</h3><p>A no-show day carries a reason and cannot contain an active attendance interval.</p></div></FeatureRow>
      </FeatureStack>
    </Split></ContentWidth></PublicSection>

    <PublicSection><ContentWidth><CtaBand $accent="plasma"><div><SectionKicker><ShieldCheckIcon /> Start with the basics</SectionKicker><h2>Build the workspace in the right order.</h2><p>Create the owner account, complete the first facility, configure its Daycare/OSC programs and rooms, then begin registering the families and children you care for.</p></div><div><PrimaryCta to="/register">Create account <ArrowRightIcon /></PrimaryCta><SecondaryCta to="/pricing">View pricing</SecondaryCta></div></CtaBand></ContentWidth></PublicSection>
  </PublicLayout>;
}
