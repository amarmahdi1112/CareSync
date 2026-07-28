import { useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BuildingOffice2Icon,
  CheckCircleIcon,
  EnvelopeIcon,
  IdentificationIcon,
  LockClosedIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UserIcon,
} from '@heroicons/react/24/outline';
import styled, { keyframes } from 'styled-components';
import { CareSyncMark } from '../../components/brand/CareSyncMark';
import { ActionButton, Eyebrow, GlassPanel, StatusChip } from '../../components/ui/Primitives';
import { useSession } from '../../auth/SessionContext';
import { validateRegisterDraft, type RegisterDraft, type RegisterErrors } from './registerValidation';

const rise = keyframes`from { opacity:0; transform:translateY(18px); } to { opacity:1; transform:translateY(0); }`;

const Page = styled.main`
  display: grid;
  min-height: 100vh;
  grid-template-columns: minmax(350px, .86fr) minmax(520px, 1.14fr);
  padding: 22px;
  @media (max-width: 980px) { grid-template-columns: 1fr; padding: 12px; }
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
    radial-gradient(circle at 32% 34%, rgba(169,120,255,.23), transparent 30%),
    radial-gradient(circle at 81% 78%, rgba(83,230,255,.12), transparent 28%),
    linear-gradient(145deg, rgba(20,25,48,.97), rgba(8,11,24,.93));
  box-shadow: ${({ theme }) => theme.shadow.panel};
  &::before, &::after { position:absolute; content:''; border:1px solid rgba(83,230,255,.13); border-radius:50%; pointer-events:none; }
  &::before { width:440px; height:440px; top:17%; right:-180px; }
  &::after { width:250px; height:250px; bottom:-80px; left:-90px; border-style:dashed; }
  @media (max-width: 980px) { display: none; }
`;

const Brand = styled(Link)`
  position: relative;
  z-index: 2;
  display: flex;
  width: max-content;
  align-items: center;
  gap: 13px;
  strong { display: block; font-family: 'CareSync Display', sans-serif; font-size: 1.1rem; font-weight: 650; }
  span { display:block; color:${({ theme }) => theme.color.textMuted}; font-size:.58rem; letter-spacing:.14em; text-transform:uppercase; }
`;

const StoryCopy = styled.div`
  position: relative;
  z-index: 2;
  h1 { margin: 15px 0 18px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2.8rem, 5vw, 5.6rem); font-weight: 500; letter-spacing: -.08em; line-height: .94; }
  > p { max-width: 550px; margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .84rem; line-height: 1.8; }
`;

const Journey = styled.div`
  display: grid;
  gap: 9px;
  margin-top: 27px;
  div { display: grid; grid-template-columns: 27px 1fr; gap: 10px; align-items:center; color:${({ theme }) => theme.color.textSoft}; font-size:.66rem; }
  span { display:grid; width:27px; height:27px; place-items:center; border:1px solid rgba(83,230,255,.22); border-radius:9px; color:${({ theme }) => theme.color.cyan}; font-size:.54rem; background:rgba(83,230,255,.04); }
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
  padding: clamp(18px, 5vw, 68px);
`;

const FormCard = styled(GlassPanel)`
  width: min(620px, 100%);
  padding: clamp(24px, 4vw, 42px);
  animation: ${rise} 420ms ${({ theme }) => theme.motion.ease} both;
`;

const MobileBrand = styled(Brand)`display:none; margin-bottom:28px; @media(max-width:980px){display:flex;}`;

const Header = styled.div`
  h1 { margin: 12px 0 7px; font-family: 'CareSync Display', sans-serif; font-size: clamp(2rem, 4vw, 3rem); font-weight: 530; letter-spacing: -.065em; }
  p { margin: 0 0 25px; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; line-height: 1.65; }
`;

const Form = styled.form`display:grid; gap:17px;`;
const FormGrid = styled.div`display:grid; grid-template-columns:1fr 1fr; gap:14px; @media(max-width:580px){grid-template-columns:1fr;}`;

const Field = styled.div<{ $wide?: boolean }>`
  display: grid;
  gap: 7px;
  ${({ $wide }) => $wide && 'grid-column: 1 / -1;'}
  label { color: ${({ theme }) => theme.color.textSoft}; font-size: .67rem; font-weight: 700; letter-spacing: .04em; }
`;

const InputWrap = styled.div`
  display: grid;
  min-height: 49px;
  grid-template-columns: 20px 1fr;
  align-items: center;
  gap: 10px;
  padding: 0 13px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 13px;
  background: rgba(255,255,255,.025);
  &:focus-within { border-color: ${({ theme }) => theme.color.cyan}; box-shadow: 0 0 0 3px rgba(83,230,255,.08); }
  svg { width:18px; color:${({ theme }) => theme.color.textMuted}; }
  input { width:100%; min-width:0; border:0; outline:0; color:${({ theme }) => theme.color.text}; background:transparent; font-size:.78rem; }
  input::placeholder { color:${({ theme }) => theme.color.textMuted}; }
`;

const FieldError = styled.span`color:${({ theme }) => theme.color.coral}; font-size:.61rem; line-height:1.45;`;

const Consent = styled.div`
  label { display:grid; grid-template-columns:18px 1fr; align-items:start; gap:10px; color:${({ theme }) => theme.color.textSoft}; font-size:.67rem; line-height:1.6; cursor:pointer; }
  input { width:17px; height:17px; margin:1px 0 0; accent-color:${({ theme }) => theme.color.plasma}; }
`;

const FormError = styled.div`
  padding: 11px 12px;
  border: 1px solid rgba(255,125,144,.24);
  border-radius: 11px;
  color: ${({ theme }) => theme.color.coral};
  background: rgba(255,125,144,.055);
  font-size: .68rem;
`;

const Submit = styled(ActionButton)`width:100%; min-height:50px;`;
const FormFooter = styled.div`
  display:flex; justify-content:space-between; align-items:center; gap:15px; margin-top:21px; padding-top:17px; border-top:1px solid ${({ theme }) => theme.color.border}; color:${({ theme }) => theme.color.textMuted}; font-size:.67rem;
  a { display:inline-flex; align-items:center; gap:6px; color:${({ theme }) => theme.color.textSoft}; font-weight:700; }
  a:hover { color:${({ theme }) => theme.color.cyan}; }
  svg { width:15px; }
  @media(max-width:500px){flex-direction:column; align-items:flex-start;}
`;

const Connected = styled.div`
  display:grid; gap:16px; text-align:center;
  > svg { width:52px; margin:0 auto; color:${({ theme }) => theme.color.mint}; }
  h1 { margin:0; font-family:'CareSync Display',sans-serif; font-size:2rem; letter-spacing:-.05em; }
  p { margin:0; color:${({ theme }) => theme.color.textMuted}; font-size:.75rem; line-height:1.6; }
`;

const INITIAL: RegisterDraft = { firstName: '', lastName: '', organizationName: '', email: '', password: '', confirmPassword: '', acceptedTerms: false };

export default function RegisterPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [values, setValues] = useState(INITIAL);
  const [errors, setErrors] = useState<RegisterErrors>({});
  const [requestError, setRequestError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const update = <Key extends keyof RegisterDraft>(key: Key, value: RegisterDraft[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => { const next = { ...current }; delete next[key]; return next; });
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateRegisterDraft(values);
    setErrors(nextErrors);
    setRequestError(null);
    const firstError = Object.keys(nextErrors)[0] as keyof RegisterDraft | undefined;
    if (firstError) {
      formRef.current?.querySelector<HTMLElement>(`[name="${firstError}"]`)?.focus();
      return;
    }
    setSubmitting(true);
    try {
      await session.register({
        email: values.email,
        password: values.password,
        firstName: values.firstName,
        lastName: values.lastName,
        organizationName: values.organizationName,
      });
      navigate('/onboarding', { replace: true });
    } catch (caught) {
      setRequestError(caught instanceof Error ? caught.message : 'CareSync could not create the account.');
    } finally { setSubmitting(false); }
  };

  return <Page>
    <Story><Brand to="/"><CareSyncMark size={48} /><div><strong>CareSync</strong><span>Childcare operations</span></div></Brand><StoryCopy><Eyebrow><SparklesIcon width={14} /> Start the Basic workspace</Eyebrow><h1>Build the record before the features.</h1><p>Create the owner identity first. Then CareSync guides the organization, first facility, licensed programs, and operating rooms into place before any family or child record is added.</p><Journey><div><span>01</span>Owner account</div><div><span>02</span>Organization and facility</div><div><span>03</span>Programs and rooms</div><div><span>04</span>Review and activate</div></Journey></StoryCopy><Safety><ShieldCheckIcon /> Protected records remain locked until setup is complete.</Safety></Story>
    <FormSide><FormCard $accent="plasma"><MobileBrand to="/"><CareSyncMark size={42} /><div><strong>CareSync</strong><span>Childcare operations</span></div></MobileBrand>
      {session.status === 'checking' ? <Connected role="status"><CareSyncMark size={58} /><StatusChip $tone="info">Checking session</StatusChip><h1>Preparing account setup.</h1><p>CareSync is checking whether this browser already has a verified owner session.</p></Connected>
        : session.status === 'unavailable' ? <Connected role="alert"><ShieldCheckIcon /><StatusChip $tone="warning">Connection unavailable</StatusChip><h1>Your saved session stayed protected.</h1><p>CareSync could not verify the saved identity. Retry it or disconnect before creating another account.</p><ActionButton $variant="primary" onClick={session.retry}><ArrowRightIcon /> Try again</ActionButton><ActionButton onClick={session.logout}>Create a different account</ActionButton></Connected>
        : session.status === 'authenticated' ? <Connected><CheckCircleIcon /><StatusChip $tone="success">Account connected</StatusChip><h1>Continue your setup.</h1><p>{session.organization?.name || 'Your owner account is ready for organization setup.'}</p><ActionButton $variant="primary" onClick={() => navigate(session.organization?.status === 'active' ? '/dashboard' : '/onboarding')}>Continue <ArrowRightIcon /></ActionButton><ActionButton onClick={session.logout}>Use a different account</ActionButton></Connected>
        : <><Header><Eyebrow><IdentificationIcon width={14} /> Owner registration</Eyebrow><h1>Create your account.</h1><p>This owner identity begins the organization setup and becomes responsible for activating the Basic workspace.</p></Header>
          <Form ref={formRef} onSubmit={submit} noValidate><FormGrid>
            <Field><label htmlFor="register-firstName">First name</label><InputWrap><UserIcon /><input id="register-firstName" name="firstName" value={values.firstName} onChange={(e) => update('firstName', e.target.value)} autoComplete="given-name" aria-invalid={Boolean(errors.firstName)} required /></InputWrap>{errors.firstName && <FieldError role="alert">{errors.firstName}</FieldError>}</Field>
            <Field><label htmlFor="register-lastName">Last name</label><InputWrap><UserIcon /><input id="register-lastName" name="lastName" value={values.lastName} onChange={(e) => update('lastName', e.target.value)} autoComplete="family-name" aria-invalid={Boolean(errors.lastName)} required /></InputWrap>{errors.lastName && <FieldError role="alert">{errors.lastName}</FieldError>}</Field>
            <Field $wide><label htmlFor="register-organizationName">Organization name <small>(optional prefill)</small></label><InputWrap><BuildingOffice2Icon /><input id="register-organizationName" name="organizationName" value={values.organizationName} onChange={(e) => update('organizationName', e.target.value)} autoComplete="organization" placeholder="You can complete this during setup" aria-invalid={Boolean(errors.organizationName)} /></InputWrap>{errors.organizationName && <FieldError role="alert">{errors.organizationName}</FieldError>}</Field>
            <Field $wide><label htmlFor="register-email">Work email</label><InputWrap><EnvelopeIcon /><input id="register-email" name="email" type="email" value={values.email} onChange={(e) => update('email', e.target.value)} autoComplete="email" placeholder="you@organization.ca" aria-invalid={Boolean(errors.email)} required /></InputWrap>{errors.email && <FieldError role="alert">{errors.email}</FieldError>}</Field>
            <Field><label htmlFor="register-password">Password</label><InputWrap><LockClosedIcon /><input id="register-password" name="password" type="password" value={values.password} onChange={(e) => update('password', e.target.value)} autoComplete="new-password" aria-invalid={Boolean(errors.password)} required /></InputWrap>{errors.password && <FieldError role="alert">{errors.password}</FieldError>}</Field>
            <Field><label htmlFor="register-confirmPassword">Confirm password</label><InputWrap><LockClosedIcon /><input id="register-confirmPassword" name="confirmPassword" type="password" value={values.confirmPassword} onChange={(e) => update('confirmPassword', e.target.value)} autoComplete="new-password" aria-invalid={Boolean(errors.confirmPassword)} required /></InputWrap>{errors.confirmPassword && <FieldError role="alert">{errors.confirmPassword}</FieldError>}</Field>
          </FormGrid>
          <Consent><label><input name="acceptedTerms" type="checkbox" checked={values.acceptedTerms} onChange={(e) => update('acceptedTerms', e.target.checked)} /><span>I confirm that I am authorized to begin setup for this organization and accept the CareSync terms and privacy notice.</span></label>{errors.acceptedTerms && <FieldError role="alert">{errors.acceptedTerms}</FieldError>}</Consent>
          {requestError && <FormError role="alert">{requestError}</FormError>}
          <Submit type="submit" $variant="primary" disabled={submitting}>{submitting ? 'Creating owner account…' : 'Create account'} {!submitting && <ArrowRightIcon />}</Submit></Form>
          <FormFooter><span>Already have an account? <Link to="/login">Sign in <ArrowRightIcon /></Link></span><Link to="/"><ArrowLeftIcon /> Back to CareSync</Link></FormFooter></>}
    </FormCard></FormSide>
  </Page>;
}
