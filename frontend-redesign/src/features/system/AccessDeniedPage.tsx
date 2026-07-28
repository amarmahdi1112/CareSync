import { Link } from 'react-router-dom';
import { LockClosedIcon } from '@heroicons/react/24/outline';
import styled from 'styled-components';
import { GlassPanel, StatusChip } from '../../components/ui/Primitives';

const Page = styled.div`display:grid;min-height:min(66vh,620px);place-items:center;padding:24px;`;
const Card = styled(GlassPanel)`width:min(520px,100%);padding:clamp(28px,6vw,48px);text-align:center;svg{width:48px;color:${({ theme }) => theme.color.amber};}h1{margin:16px 0 8px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.55rem,4vw,2.15rem);font-weight:600;}p{margin:0 auto 22px;max-width:42ch;color:${({ theme }) => theme.color.textMuted};font-size:.82rem;line-height:1.75;}a{display:inline-flex;min-height:44px;align-items:center;padding:0 18px;border:1px solid ${({ theme }) => theme.color.borderStrong};border-radius:7px 13px 7px 13px;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};}`;

export default function AccessDeniedPage() {
  return <Page><Card $accent="amber"><LockClosedIcon aria-hidden="true" /><div><StatusChip $tone="warning">Access limited</StatusChip></div><h1>This area is outside your role.</h1><p>Your account remains secure. Ask the organization owner to update your role or room assignments if you need this workspace.</p><Link to="/dashboard">Return to dashboard</Link></Card></Page>;
}
