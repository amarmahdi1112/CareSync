import styled from 'styled-components';
import { GlassPanel } from '../../components/ui/Primitives';

export const CredentialPage = styled.main`display:grid;min-height:100vh;place-items:center;padding:clamp(18px,5vw,48px);`;
export const CredentialCard = styled(GlassPanel)`display:grid;width:min(560px,100%);gap:18px;padding:clamp(24px,5vw,42px);h1{margin:7px 0 5px;font-family:'CareSync Display',sans-serif;font-size:clamp(1.55rem,4vw,2.2rem);font-weight:600;letter-spacing:-.045em;}p{margin:0;color:${({ theme }) => theme.color.textMuted};font-size:.8rem;line-height:1.7;}`;
export const Summary = styled.div`display:grid;gap:7px;padding:14px;border:1px solid ${({ theme }) => theme.color.border};border-radius:9px 15px 9px 15px;background:${({ theme }) => theme.color.surfaceStrong};strong{font-size:.88rem;font-weight:600;}span{color:${({ theme }) => theme.color.textMuted};font-size:.75rem;}`;
export const CredentialForm = styled.form`display:grid;gap:14px;`;
export const CredentialField = styled.label`display:grid;gap:7px;color:${({ theme }) => theme.color.textSoft};font-size:.76rem;font-weight:600;input{min-height:46px;padding:0 13px;border:1px solid ${({ theme }) => theme.color.controlBorder};border-radius:7px 13px 7px 13px;outline:0;color:${({ theme }) => theme.color.text};background:${({ theme }) => theme.color.control};font:inherit;&:focus{border-color:${({ theme }) => theme.color.cyan};}}`;
export const CredentialNotice = styled.div<{ $error?: boolean }>`display:flex;gap:9px;padding:12px 13px;border:1px solid ${({ $error, theme }) => $error ? theme.color.coral : theme.color.borderStrong};border-radius:8px 13px 8px 13px;color:${({ $error, theme }) => $error ? theme.color.coral : theme.color.textSoft};background:${({ theme }) => theme.color.surfaceStrong};font-size:.77rem;line-height:1.55;svg{width:18px;flex:0 0 auto;}`;
export const CredentialActions = styled.div`display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;`;
