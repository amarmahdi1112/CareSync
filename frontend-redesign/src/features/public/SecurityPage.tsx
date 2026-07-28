import {
  ArrowRightIcon, CheckCircleIcon, CircleStackIcon, ClipboardDocumentCheckIcon,
  KeyIcon, LockClosedIcon, ShieldCheckIcon, UserGroupIcon,
} from '@heroicons/react/24/outline';
import {
  ContentWidth, PrimaryCta, PublicLayout, PublicSection, SecondaryCta,
  SectionKicker, SectionLead, SectionTitle,
} from '../../components/public/PublicLayout';
import { CenterKicker, CtaBand, FeatureRow, FeatureStack, InfoCard, InfoGrid, InteriorHero, Split, TruthNote } from './publicPageStyles';

export default function SecurityPage() {
  return <PublicLayout>
    <InteriorHero><ContentWidth><CenterKicker><SectionKicker><ShieldCheckIcon /> Security foundation</SectionKicker></CenterKicker><h1>Childcare records deserve explicit boundaries.</h1><p>CareSync Basic is designed to fail closed: identity, organization, facility, and record ownership must agree before protected information is read or changed.</p></ContentWidth></InteriorHero>

    <PublicSection><ContentWidth>
      <SectionKicker><LockClosedIcon /> Tenant isolation</SectionKicker><SectionTitle>Ownership is checked at every layer.</SectionTitle><SectionLead>A signed-in user is not enough. Every workspace request must resolve through an active organization membership, and facility-owned records must remain inside that organization.</SectionLead>
      <InfoGrid>
        <InfoCard $accent="plasma"><KeyIcon /><h2>Authenticated identity</h2><p>Protected routes wait for the saved session to be verified. Missing or expired identity returns to sign-in without requesting daycare records.</p></InfoCard>
        <InfoCard $accent="cyan"><UserGroupIcon /><h2>Organization membership</h2><p>Membership determines the active tenant. Missing or mismatched organization context blocks the request instead of falling back to unscoped data.</p></InfoCard>
        <InfoCard $accent="amber"><CircleStackIcon /><h2>Database boundary</h2><p>The Basic architecture requires organization filtering in the API and PostgreSQL row-level security as an independent second boundary.</p></InfoCard>
      </InfoGrid>
    </ContentWidth></PublicSection>

    <PublicSection><ContentWidth><Split>
      <div><SectionKicker><ClipboardDocumentCheckIcon /> Traceable operations</SectionKicker><SectionTitle>Corrections should explain themselves.</SectionTitle><SectionLead>Basic mutations are expected to carry the responsible actor and produce audit evidence. Attendance corrections preserve the reason and before/after state rather than silently replacing history.</SectionLead><TruthNote><ShieldCheckIcon /><span>CareSync is not the Government of Alberta and does not issue licences, determine eligibility, or replace official systems.</span></TruthNote></div>
      <FeatureStack>
        <FeatureRow $accent="cyan"><CheckCircleIcon /><div><h3>Fail-closed loading</h3><p>Unavailable identity or organization metadata locks the affected screen and offers a deliberate retry.</p></div></FeatureRow>
        <FeatureRow $accent="plasma"><CheckCircleIcon /><div><h3>Cross-tenant references rejected</h3><p>A valid identifier from another organization must not reveal, link, or mutate its record.</p></div></FeatureRow>
        <FeatureRow $accent="cyan"><CheckCircleIcon /><div><h3>Actual attendance isolated</h3><p>Daily check-in records remain separate from planning information and every synthetic data source.</p></div></FeatureRow>
        <FeatureRow $accent="amber"><CheckCircleIcon /><div><h3>Minimal Basic surface</h3><p>Deferred modules expose no navigation item, shortcut, search result, or usable direct route.</p></div></FeatureRow>
      </FeatureStack>
    </Split></ContentWidth></PublicSection>

    <PublicSection><ContentWidth><CtaBand $accent="plasma"><div><SectionKicker><ShieldCheckIcon /> Begin with a clean boundary</SectionKicker><h2>Create the organization before its records.</h2><p>The guided setup establishes the owner, organization, first facility, licensed programs, and operating rooms before family and child data enter the workspace.</p></div><div><PrimaryCta to="/register">Create account <ArrowRightIcon /></PrimaryCta><SecondaryCta to="/product">See the product</SecondaryCta></div></CtaBand></ContentWidth></PublicSection>
  </PublicLayout>;
}
