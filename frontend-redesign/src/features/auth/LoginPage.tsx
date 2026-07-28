import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  EnvelopeIcon,
  LockClosedIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { CareSyncMark } from '../../components/brand/CareSyncMark';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useSession } from '../../auth/SessionContext';
import { safeReturnPath } from '../../auth/routeGuardModel';
import { OrganizationSelectionRequiredError, type OrganizationChoice } from '../../api/client';

const rise = keyframes`from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:translateY(0); }`;
const orbit = keyframes`to { transform: rotate(360deg); }`;

const Page = styled.main`
  display: grid;
  min-height: 100vh;
  grid-template-columns: minmax(340px, .9fr) minmax(430px, 1.1fr);
  padding: 22px;
  @media (max-width: 880px) { grid-template-columns: 1fr; padding: 12px; }
`;

const Story = styled.section`
  position: relative;
  display: flex;
  min-height: calc(100vh - 44px);
  flex-direction: column;
  justify-content: space-between;
  padding: clamp(28px, 5vw, 66px);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 30px;
  background:
    radial-gradient(circle at 38% 40%, rgba(169,120,255,.22), transparent 28%),
    radial-gradient(circle at 83% 72%, rgba(83,230,255,.12), transparent 30%),
    linear-gradient(145deg, rgba(20,25,48,.97), rgba(8,11,24,.93));
  box-shadow: ${({ theme }) => theme.shadow.panel};

  &::before {
    position: absolute;
    top: 30%;
    left: 50%;
    width: min(40vw, 480px);
    aspect-ratio: 1;
    content: '';
    border: 1px dashed rgba(83,230,255,.22);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    animation: ${orbit} 28s linear infinite;
  }

  @media (max-width: 880px) { display: none; }
`;

const Brand = styled(Link)`
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 13px;
  strong { display: block; font-family: 'CareSync Display', sans-serif; font-size: 1.1rem; font-weight: 650; }
  span { display:block; color:${({ theme }) => theme.color.textMuted}; font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; }
`;

const StoryCopy = styled.div`
  position: relative;
  z-index: 2;
  max-width: 660px;
  h1 { margin: 15px 0 18px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2.4rem, 5vw, 5.8rem); font-weight: 500; letter-spacing: -.08em; line-height: .94; }
  p { max-width: 550px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .86rem; line-height: 1.8; }
`;

const Safety = styled.div`
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 10px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .68rem;
  svg { width: 18px; color: ${({ theme }) => theme.color.mint}; }
`;

const FormSide = styled.section`
  display: grid;
  min-height: calc(100vh - 44px);
  place-items: center;
  padding: clamp(20px, 6vw, 80px);
`;

const FormCard = styled(GlassPanel)`
  width: min(470px, 100%);
  padding: clamp(24px, 4vw, 42px);
  animation: ${rise} 420ms ${({ theme }) => theme.motion.ease} both;
`;

const MobileBrand = styled(Brand)`
  display: none;
  margin-bottom: 28px;
  @media (max-width: 880px) { display: flex; }
`;

const FormHeader = styled.div`
  h2 { margin: 12px 0 7px; font-family: 'CareSync Display', sans-serif; font-size: clamp(1.8rem, 4vw, 2.7rem); font-weight: 530; letter-spacing: -.06em; }
  p { margin: 0 0 26px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.6; }
`;

const Form = styled.form`
  display: grid;
  gap: 17px;
`;

const Field = styled.label`
  display: grid;
  gap: 7px;
  > span { color: ${({ theme }) => theme.color.textSoft}; font-size: .67rem; font-weight: 700; letter-spacing: .05em; }
`;

const InputWrap = styled.div`
  display: grid;
  grid-template-columns: 20px 1fr;
  align-items: center;
  gap: 10px;
  min-height: 50px;
  padding: 0 14px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px;
  background: rgba(255,255,255,.025);
  transition: border-color 150ms ease, box-shadow 150ms ease;
  &:focus-within { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px rgba(83,230,255,.08); }
  svg { width: 19px; color: ${({ theme }) => theme.color.textMuted}; }
  input { width: 100%; min-width: 0; border: 0; outline: 0; color: ${({ theme }) => theme.color.text}; background: transparent; font-size: .82rem; }
  input::placeholder { color: ${({ theme }) => theme.color.textMuted}; }
`;

const ErrorMessage = styled.div`
  padding: 11px 12px;
  border: 1px solid rgba(255,125,144,.24);
  border-radius: 11px;
  color: ${({ theme }) => theme.color.coral};
  background: rgba(255,125,144,.055);
  font-size: .68rem;
`;

const Submit = styled(ActionButton)`
  width: 100%;
  min-height: 50px;
  margin-top: 3px;
`;

const FormFooter = styled.div`
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 22px;
  padding-top: 17px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .67rem;
  a { display: inline-flex; align-items: center; gap: 6px; color: ${({ theme }) => theme.color.textSoft}; font-weight: 700; }
  a:hover { color: ${({ theme }) => theme.color.cyan}; }
  svg { width: 15px; }
  @media (max-width: 460px) { flex-direction: column; }
`;

const Connected = styled.div`
  display: grid;
  gap: 16px;
  text-align: center;
  > svg { width: 52px; margin: 0 auto; color: ${({ theme }) => theme.color.mint}; }
  h2 { margin: 0; font-family: 'CareSync Display', sans-serif; font-size: 2rem; font-weight: 540; letter-spacing: -.05em; }
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
`;

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [organizationChoices, setOrganizationChoices] = useState<OrganizationChoice[]>([]);
  const availableOrganizations = organizationChoices.length ? organizationChoices : session.organizationChoices;
  const returnTo = safeReturnPath((location.state as { from?: unknown } | null)?.from);

  const authenticate = async (organizationId?: string) => {
    setError(null); setSubmitting(true);
    try {
      await session.login(email.trim(), password, organizationId);
      navigate(returnTo, { replace: true });
    } catch (caught) {
      if (caught instanceof OrganizationSelectionRequiredError) setOrganizationChoices(caught.organizations);
      else setError(caught instanceof Error ? caught.message : 'The secure session could not be started.');
    } finally {
      setSubmitting(false);
    }
  };
  const submit = async (event: FormEvent) => { event.preventDefault(); setOrganizationChoices([]); await authenticate(); };
  const chooseOrganization = async (choice: OrganizationChoice) => {
    if (organizationChoices.length) return authenticate(choice.organization_id);
    setSubmitting(true); setError(null);
    try { await session.switchOrganization(choice.organization_id); navigate(returnTo, { replace: true }); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'The organization could not be selected.'); }
    finally { setSubmitting(false); }
  };

  return (
    <Page>
      <Story>
        <Brand to="/"><CareSyncMark size={48} /><div><strong>CareSync</strong><span>Childcare operations</span></div></Brand>
        <StoryCopy><Eyebrow><SparklesIcon width={14} /> Welcome back</Eyebrow><h1>Return to a clear operating day.</h1><p>Connect to your organization workspace to manage facilities, rooms, families, children, enrollment, and actual daily attendance.</p></StoryCopy>
        <Safety><ShieldCheckIcon /> Protected records stay locked until your identity and organization are verified.</Safety>
      </Story>
      <FormSide>
        <FormCard $accent="plasma">
          <MobileBrand to="/"><CareSyncMark size={43} /><div><strong>CareSync</strong><span>Childcare operations</span></div></MobileBrand>
          {session.status === 'checking' ? (
            <Connected role="status">
              <CareSyncMark size={58} />
              <StatusChip $tone="info">Checking saved session</StatusChip>
              <h2>Verifying the secure link.</h2>
              <p>CareSync is confirming your saved identity before opening protected records.</p>
            </Connected>
          ) : session.status === 'unavailable' ? (
            <Connected role="alert">
              <ShieldCheckIcon />
              <StatusChip $tone="warning">Connection unavailable</StatusChip>
              <h2>Your saved session was not erased.</h2>
              <p>CareSync could not confirm the saved session. Your token was retained and no organization records were requested.</p>
              <ActionButton $variant="primary" onClick={session.retry}><ArrowRightIcon /> Try again</ActionButton>
              <ActionButton onClick={() => session.logout()}>Sign in with another account</ActionButton>
            </Connected>
          ) : session.status === 'authenticated' ? (
            <Connected>
              <CheckCircleIcon />
              <StatusChip $tone="success">Secure session active</StatusChip>
              <h2>Welcome back, {session.user?.first_name || 'operator'}.</h2>
              <p>{session.organization?.name || 'Your identity is connected. Organization details are still loading.'}</p>
              <ActionButton $variant="primary" onClick={() => navigate(returnTo)}>Enter workspace <ArrowRightIcon /></ActionButton>
              <ActionButton onClick={session.logout}>Disconnect session</ActionButton>
            </Connected>
          ) : (
            <>
              <FormHeader><Eyebrow><LockClosedIcon width={14} /> Secure workspace</Eyebrow><h2>Sign in to CareSync.</h2><p>Use the owner account associated with your childcare organization.</p></FormHeader>
              <Form onSubmit={submit}>
                {availableOrganizations.length > 0 && <div role="group" aria-label="Choose organization"><p>This identity belongs to more than one organization. Choose the workspace to open.</p>{availableOrganizations.map((choice) => <ActionButton key={choice.organization_id} type="button" disabled={submitting} onClick={() => void chooseOrganization(choice)}>{choice.organization_name} · {choice.role_key}</ActionButton>)}</div>}
                <Field htmlFor="login-email"><span>Email address</span><InputWrap><EnvelopeIcon /><input id="login-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" placeholder="you@organization.ca" required /></InputWrap></Field>
                <Field htmlFor="login-password"><span>Password</span><InputWrap><LockClosedIcon /><input id="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="Enter your password" required /></InputWrap></Field>
                {error && <ErrorMessage role="alert">{error}</ErrorMessage>}
                <Submit type="submit" $variant="primary" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'} {!submitting && <ArrowRightIcon />}</Submit>
              </Form>
              <FormFooter><span>New to CareSync? <Link to="/register">Create an account <ArrowRightIcon /></Link></span><Link to="/"><ArrowLeftIcon /> Back to CareSync</Link></FormFooter>
            </>
          )}
        </FormCard>
      </FormSide>
    </Page>
  );
}
