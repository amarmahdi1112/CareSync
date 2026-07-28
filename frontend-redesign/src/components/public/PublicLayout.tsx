import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import {
  ArrowRightIcon,
  Bars3Icon,
  MapPinIcon,
  ShieldCheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled, { css } from 'styled-components';
import { CareSyncMark } from '../brand/CareSyncMark';

const navItems = [
  { to: '/product', label: 'Product' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/security', label: 'Security' },
];

const SkipLink = styled.a`
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 100;
  padding: 10px 14px;
  border-radius: ${({ theme }) => theme.radius.sm};
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.color.cyan};
  font-weight: 800;
  transform: translateY(-160%);
  &:focus { transform: translateY(0); }
`;

const Site = styled.div`
  position: relative;
  min-height: 100vh;
  overflow: clip;
  isolation: isolate;
`;

const Header = styled.header`
  position: relative;
  z-index: 30;
  width: min(1240px, calc(100% - 32px));
  margin: 18px auto 0;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 18px;
  background: rgba(8, 11, 24, .76);
  box-shadow: 0 18px 60px rgba(0, 0, 0, .24);
  backdrop-filter: blur(24px) saturate(130%);
`;

const HeaderInner = styled.div`
  display: grid;
  min-height: 70px;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 24px;
  padding: 0 14px 0 20px;
  @media (max-width: 760px) { grid-template-columns: 1fr auto; }
`;

const Brand = styled(Link)`
  display: inline-flex;
  width: max-content;
  align-items: center;
  gap: 11px;
  strong { display: block; font-family: 'CareSync Display', sans-serif; font-size: 1.02rem; font-weight: 680; letter-spacing: -.03em; }
  span { display: block; margin-top: 1px; color: ${({ theme }) => theme.color.textMuted}; font-size: .52rem; font-weight: 750; letter-spacing: .16em; text-transform: uppercase; }
`;

const DesktopNav = styled.nav`
  display: flex;
  align-items: center;
  gap: 5px;
  a {
    padding: 9px 12px;
    border-radius: 10px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: .76rem;
    font-weight: 650;
    transition: color 150ms ease, background 150ms ease;
  }
  a:hover, a[aria-current='page'] { color: ${({ theme }) => theme.color.text}; background: rgba(255,255,255,.055); }
  @media (max-width: 760px) { display: none; }
`;

const HeaderActions = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  @media (max-width: 760px) { display: none; }
`;

const TextLink = styled(Link)`
  padding: 10px 12px;
  color: ${({ theme }) => theme.color.textSoft};
  font-size: .75rem;
  font-weight: 700;
  &:hover { color: ${({ theme }) => theme.color.text}; }
`;

const StartLink = styled(Link)`
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid rgba(198,168,255,.48);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(169,120,255,.95), rgba(91,83,207,.92));
  box-shadow: 0 10px 28px rgba(120,83,221,.23);
  font-size: .75rem;
  font-weight: 760;
  transition: transform 150ms ease, filter 150ms ease;
  &:hover { transform: translateY(-1px); filter: brightness(1.08); }
  svg { width: 17px; }
`;

const MenuButton = styled.button`
  display: none;
  width: 43px;
  height: 43px;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.text};
  background: rgba(255,255,255,.035);
  cursor: pointer;
  svg { width: 20px; }
  @media (max-width: 760px) { display: grid; }
`;

const MobileNav = styled.nav<{ $open: boolean }>`
  display: none;
  padding: 0 14px 14px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  a {
    display: flex;
    min-height: 46px;
    align-items: center;
    padding: 0 12px;
    border-radius: 10px;
    color: ${({ theme }) => theme.color.textSoft};
    font-size: .79rem;
    font-weight: 700;
  }
  a:hover, a[aria-current='page'] { color: ${({ theme }) => theme.color.text}; background: rgba(255,255,255,.05); }
  ${StartLink} { margin-top: 6px; color: white; }
  @media (max-width: 760px) { ${({ $open }) => $open && css`display: grid;`} }
`;

const Footer = styled.footer`
  position: relative;
  z-index: 2;
  width: min(1180px, calc(100% - 40px));
  margin: 70px auto 0;
  padding: 36px 0 28px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
`;

const FooterGrid = styled.div`
  display: grid;
  grid-template-columns: 1.4fr repeat(2, minmax(130px, .5fr));
  gap: 40px;
  @media (max-width: 700px) { grid-template-columns: 1fr 1fr; }
  @media (max-width: 480px) { grid-template-columns: 1fr; }
`;

const FooterBrand = styled.div`
  max-width: 440px;
  p { margin: 13px 0 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .71rem; line-height: 1.7; }
  @media (max-width: 700px) { grid-column: 1 / -1; }
`;

const FooterLinks = styled.div`
  h2 { margin: 0 0 10px; color: ${({ theme }) => theme.color.text}; font-size: .66rem; letter-spacing: .12em; text-transform: uppercase; }
  a { display: block; width: max-content; padding: 5px 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .7rem; }
  a:hover { color: ${({ theme }) => theme.color.cyan}; }
`;

const Footnote = styled.div`
  display: flex;
  justify-content: space-between;
  gap: 24px;
  margin-top: 30px;
  padding-top: 18px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .6rem;
  span { display: inline-flex; align-items: center; gap: 7px; }
  svg { width: 14px; color: ${({ theme }) => theme.color.mint}; }
  @media (max-width: 600px) { flex-direction: column; gap: 8px; }
`;

export const PublicMain = styled.main`
  position: relative;
  z-index: 1;
`;

export const ContentWidth = styled.div`
  width: min(1180px, calc(100% - 40px));
  margin-inline: auto;
`;

export const PublicSection = styled.section`
  padding: clamp(64px, 9vw, 112px) 0;
`;

export const SectionKicker = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: ${({ theme }) => theme.color.cyan};
  font-size: .65rem;
  font-weight: 780;
  letter-spacing: .17em;
  text-transform: uppercase;
  svg { width: 16px; }
`;

export const SectionTitle = styled.h2`
  max-width: 780px;
  margin: 15px 0 14px;
  font-family: 'CareSync Display', sans-serif;
  font-size: clamp(2rem, 5vw, 4rem);
  font-weight: 520;
  letter-spacing: -.07em;
  line-height: 1.03;
`;

export const SectionLead = styled.p`
  max-width: 680px;
  margin: 0;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: clamp(.78rem, 1.4vw, .92rem);
  line-height: 1.82;
`;

export const PrimaryCta = styled(Link)`
  display: inline-flex;
  min-height: 50px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 0 20px;
  border: 1px solid rgba(198,168,255,.5);
  border-radius: 14px;
  background: linear-gradient(135deg, #a978ff, #6658d6);
  box-shadow: 0 14px 38px rgba(120,83,221,.28);
  font-size: .8rem;
  font-weight: 780;
  transition: transform 150ms ease, filter 150ms ease;
  &:hover { transform: translateY(-2px); filter: brightness(1.08); }
  svg { width: 18px; }
`;

export const SecondaryCta = styled(Link)`
  display: inline-flex;
  min-height: 50px;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 0 20px;
  border: 1px solid ${({ theme }) => theme.color.border};
  border-radius: 14px;
  color: ${({ theme }) => theme.color.textSoft};
  background: rgba(255,255,255,.025);
  font-size: .8rem;
  font-weight: 720;
  &:hover { color: ${({ theme }) => theme.color.text}; border-color: ${({ theme }) => theme.color.borderStrong}; }
`;

export function PublicLayout({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <Site>
      <SkipLink href="#public-content">Skip to content</SkipLink>
      <Header>
        <HeaderInner>
          <Brand to="/" aria-label="CareSync home"><CareSyncMark size={40} /><div><strong>CareSync</strong><span>Childcare operations</span></div></Brand>
          <DesktopNav aria-label="Public navigation">
            {navItems.map((item) => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}
          </DesktopNav>
          <HeaderActions><TextLink to="/login">Sign in</TextLink><StartLink to="/register">Start your workspace <ArrowRightIcon /></StartLink></HeaderActions>
          <MenuButton type="button" onClick={() => setMenuOpen((open) => !open)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen}>{menuOpen ? <XMarkIcon /> : <Bars3Icon />}</MenuButton>
        </HeaderInner>
        <MobileNav $open={menuOpen} aria-label="Mobile public navigation">
          {navItems.map((item) => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}
          <NavLink to="/login">Sign in</NavLink>
          <StartLink to="/register">Start your workspace <ArrowRightIcon /></StartLink>
        </MobileNav>
      </Header>
      <PublicMain id="public-content" tabIndex={-1}>{children}</PublicMain>
      <Footer>
        <FooterGrid>
          <FooterBrand><Brand to="/"><CareSyncMark size={38} /><div><strong>CareSync</strong><span>Childcare operations</span></div></Brand><p>A calm operating foundation for Alberta childcare organizations—starting with enrollment, rooms, family records, and daily attendance.</p></FooterBrand>
          <FooterLinks><h2>Explore</h2><Link to="/product">Product</Link><Link to="/pricing">Pricing</Link><Link to="/security">Security</Link></FooterLinks>
          <FooterLinks><h2>Workspace</h2><Link to="/register">Register</Link><Link to="/login">Sign in</Link></FooterLinks>
        </FooterGrid>
        <Footnote><span><MapPinIcon /> Alberta-first, Canada-ready</span><span><ShieldCheckIcon /> Built around clear organization boundaries</span></Footnote>
      </Footer>
    </Site>
  );
}
