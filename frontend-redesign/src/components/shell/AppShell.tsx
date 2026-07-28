import { useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowRightOnRectangleIcon,
  Bars3BottomLeftIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  CommandLineIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import styled, { css } from 'styled-components';
import { CareSyncMark } from '../brand/CareSyncMark';
import { IconButton, StatusChip } from '../ui/Primitives';
import { buildNavigation, findNavigationItem, searchNavigation, type NavigationItem } from '../../data/navigation';
import { useShellStore } from '../../state/useShellStore';
import { api } from '../../api/client';
import { useSession } from '../../auth/SessionContext';
import { useMotion, WorkspaceMotionLayer } from '../../motion';
import { NotificationInbox } from '../../features/notifications/NotificationInbox';
import { useRealtimeState } from '../../realtime/RealtimeContext';
import { ChildcareCommandRecoverySurface } from '../../childcare-commands/ChildcareCommandRecoverySurface';
import { useTransportRegistryCapability } from '../../features/transport-registry/capability';
import { useBillingCapability } from '../../features/billing/billingCapability';

function useAuthorizedNavigation() {
  const session = useSession();
  const transportRegistry = useTransportRegistryCapability();
  const billing = useBillingCapability();
  return useMemo(
    () => {
      const capabilities = new Set<'transport_registry' | 'billing_ledger'>();
      if (transportRegistry.enabled) capabilities.add('transport_registry');
      if (billing.enabled) capabilities.add('billing_ledger');
      return buildNavigation(session.user, capabilities, {
        billing: billing.live ? 'live' : 'preview',
      });
    },
    [billing.enabled, billing.live, session.user, transportRegistry.enabled],
  );
}

const Shell = styled.div<{ $collapsed: boolean }>`
  display: grid;
  min-height: 100vh;
  grid-template-columns: ${({ $collapsed, theme }) => $collapsed ? theme.layout.railCollapsed : theme.layout.rail} minmax(0, 1fr);
  color: ${({ theme }) => theme.color.text};
  background: ${({ theme }) => theme.color.canvas};
  isolation: isolate;
  transition: grid-template-columns ${({ theme }) => theme.motion.slow} ${({ theme }) => theme.motion.ease};

  @media (max-width: ${({ theme }) => theme.breakpoint.tablet}) {
    grid-template-columns: ${({ theme }) => theme.layout.railCollapsed} minmax(0, 1fr);
  }

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) {
    display: block;
  }
`;

const SkipLink = styled.a`
  position: fixed;
  top: 10px;
  left: 10px;
  z-index: 1000;
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  padding: 0 16px;
  border-radius: 6px 12px 6px 12px;
  color: ${({ theme }) => theme.color.ink};
  background: ${({ theme }) => theme.color.cyan};
  font-weight: 600;
  transform: translateY(-180%);
  transition: transform 120ms ease;
  &:focus { transform: translateY(0); }
`;

const Rail = styled.aside<{ $collapsed: boolean; $mobileOpen: boolean }>`
  position: sticky;
  top: 0;
  z-index: 210;
  display: flex;
  width: 100%;
  height: 100vh;
  min-width: 0;
  flex-direction: column;
  border-right: 1px solid ${({ theme }) => theme.color.border};
  border-bottom-right-radius: 16px;
  background: linear-gradient(
      180deg,
      color-mix(in srgb, ${({ theme }) => theme.color.canvasElevated} 96%, ${({ theme }) => theme.color.plasma}),
      ${({ theme }) => theme.color.canvasElevated} 28%
    );
  box-shadow: 8px 0 26px rgba(4, 10, 20, .14);

  &::before {
    position: absolute;
    top: 22px;
    right: -1px;
    width: 2px;
    height: 126px;
    content: '';
    background: linear-gradient(180deg, ${({ theme }) => theme.color.cyan}, ${({ theme }) => theme.color.plasma}, transparent);
    box-shadow: 0 0 2px ${({ theme }) => theme.color.plasma};
  }

  @media (max-width: ${({ theme }) => theme.breakpoint.tablet}) and (min-width: 721px) {
    ${({ $collapsed, theme }) => !$collapsed && css`width: 278px; box-shadow: ${theme.shadow.panel};`}
  }

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) {
    position: fixed;
    left: 0;
    width: min(86vw, 318px);
    border-radius: 0 16px 16px 0;
    transform: translateX(${({ $mobileOpen }) => $mobileOpen ? '0' : '-105%'});
    transition: transform ${({ theme }) => theme.motion.slow} ${({ theme }) => theme.motion.ease};
    box-shadow: ${({ theme }) => theme.shadow.panel};
  }
`;

const Brand = styled.div<{ $collapsed: boolean }>`
  display: flex;
  height: ${({ theme }) => theme.layout.header};
  align-items: center;
  gap: 12px;
  padding: ${({ $collapsed }) => $collapsed ? '0 22px' : '0 20px'};
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: color-mix(in srgb, ${({ theme }) => theme.color.canvasElevated} 95%, ${({ theme }) => theme.color.cyan});
  overflow: hidden;
`;

const BrandCopy = styled.div<{ $hidden: boolean }>`
  min-width: 0;
  opacity: ${({ $hidden }) => $hidden ? 0 : 1};
  transform: translateX(${({ $hidden }) => $hidden ? '-8px' : '0'});
  transition: opacity 150ms ease, transform 190ms ease;
  white-space: nowrap;

  strong {
    display: block;
    font-family: 'CareSync Display', ui-rounded, sans-serif;
    font-size: 1.04rem;
    font-weight: 600;
    letter-spacing: -.03em;
  }
  span { display: block; color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }
`;

const NavScroll = styled.nav`
  flex: 1;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 16px 12px;
`;

const Group = styled.div`
  & + & { margin-top: 20px; }
`;

const GroupLabel = styled.p<{ $hidden: boolean }>`
  height: ${({ $hidden }) => $hidden ? '1px' : '18px'};
  margin: 0 10px 7px;
  overflow: hidden;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: .72rem;
  font-weight: 600;
  letter-spacing: .08em;
  opacity: ${({ $hidden }) => $hidden ? 0 : 1};
  text-transform: uppercase;
  white-space: nowrap;
  transition: opacity 120ms ease;
`;

const NavItem = styled.span<{ $active: boolean; $collapsed: boolean }>`
  position: relative;
  display: flex;
  min-height: 48px;
  align-items: center;
  gap: 12px;
  padding: ${({ $collapsed }) => $collapsed ? '0 17px' : '0 14px'};
  overflow: hidden;
  border: 1px solid ${({ $active, theme }) => $active ? theme.color.borderStrong : 'transparent'};
  border-radius: 7px 13px 7px 13px;
  color: ${({ $active, theme }) => $active ? theme.color.text : theme.color.textMuted};
  background: ${({ $active, theme }) => $active
    ? `linear-gradient(90deg, color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.plasma}), color-mix(in srgb, ${theme.color.surfaceStrong} 94%, ${theme.color.cyan}))`
    : 'transparent'};
  transition: color ${({ theme }) => theme.motion.fast} ease, background ${({ theme }) => theme.motion.fast} ease, border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;

  &::before {
    position: absolute;
    left: -1px;
    width: 2px;
    height: 22px;
    content: '';
    border-radius: 4px;
    background: ${({ $active, theme }) => $active ? theme.color.cyan : 'transparent'};
    box-shadow: ${({ $active, theme }) => $active ? `0 0 2px ${theme.color.cyan}` : 'none'};
  }

  &:hover { color: ${({ theme }) => theme.color.text}; background: ${({ theme }) => theme.color.surfaceHover}; transform: translateX(1px); }
  svg { width: 20px; height: 20px; flex: 0 0 auto; stroke-width: 1.6; }
`;

const NavCopy = styled.span<{ $hidden: boolean }>`
  display: block;
  min-width: 0;
  opacity: ${({ $hidden }) => $hidden ? 0 : 1};
  transition: opacity 120ms ease;
  white-space: nowrap;
  strong { display: block; overflow: hidden; font-size: .8125rem; font-weight: 600; text-overflow: ellipsis; }
  small { display: block; overflow: hidden; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; text-overflow: ellipsis; }
`;

const UtilityArea = styled.div`
  padding: 11px 12px 10px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  background: color-mix(in srgb, ${({ theme }) => theme.color.canvasElevated} 96%, ${({ theme }) => theme.color.plasma});
`;

const RailToggleArea = styled.div<{ $collapsed: boolean }>`
  display: flex;
  justify-content: ${({ $collapsed }) => $collapsed ? 'center' : 'flex-end'};
  padding: 8px 12px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.canvasElevated};

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) {
    display: none;
  }
`;

const Profile = styled.div<{ $collapsed: boolean }>`
  display: flex;
  min-height: 66px;
  align-items: center;
  gap: 10px;
  padding: ${({ $collapsed }) => $collapsed ? '10px 21px' : '10px 16px'};
  overflow: hidden;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.canvasElevated};
`;

const Avatar = styled.div`
  display: grid;
  width: 37px;
  height: 37px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 12px;
  color: ${({ theme }) => theme.color.plasmaBright};
  background: linear-gradient(135deg, color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 84%, ${({ theme }) => theme.color.plasma}), color-mix(in srgb, ${({ theme }) => theme.color.surfaceStrong} 92%, ${({ theme }) => theme.color.cyan}));
  box-shadow: 0 0 2px ${({ theme }) => theme.color.plasma};
  font-family: 'CareSync Display', sans-serif;
  font-size: .78rem;
  font-weight: 600;
`;

const ProfileCopy = styled(BrandCopy)`
  flex: 1;
  strong { font-family: inherit; font-size: .78rem; letter-spacing: 0; }
  span { font-size: .72rem; }
`;

const ProfileIdentity = styled.div<{ $hidden: boolean }>`
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 10px;
  overflow: hidden;
  ${({ $hidden }) => $hidden && css`display: none;`}
`;

const ProfileSignOutButton = styled(IconButton)`
  width: 44px;
  height: 44px;
  color: ${({ theme }) => theme.color.textSoft};

  &:hover {
    border-color: ${({ theme }) => theme.color.coral};
    color: ${({ theme }) => theme.color.coral};
    background: color-mix(in srgb, ${({ theme }) => theme.color.control} 90%, ${({ theme }) => theme.color.coral});
  }

  &:disabled { cursor: progress; opacity: .58; }
`;

const RailCollapseButton = styled(IconButton)`
  width: 44px;
  height: 44px;
  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) { display: none; }
`;

const MobileClose = styled(IconButton)`
  display: none;
  width: 44px;
  height: 44px;
  margin-left: auto;
  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) { display: inline-grid; }
`;

const Main = styled.div`
  position: relative;
  isolation: isolate;
  min-width: 0;
  min-height: 100vh;
  background: ${({ theme }) => theme.color.canvas};
`;

const Header = styled.header`
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  height: ${({ theme }) => theme.layout.header};
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 clamp(16px, 2.4vw, 38px);
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: linear-gradient(90deg, ${({ theme }) => theme.color.canvasElevated}, color-mix(in srgb, ${({ theme }) => theme.color.canvasElevated} 96%, ${({ theme }) => theme.color.plasma}));
  box-shadow: 0 8px 22px rgba(4, 10, 20, .10);

  /* NotificationInbox is anchored here and must be able to escape the header box. */

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) { height: 66px; }
`;

const HeaderLeft = styled.div`
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 13px;
`;

const MobileMenu = styled(IconButton)`
  display: none;
  width: 44px;
  height: 44px;
  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) { display: inline-grid; }
`;

const Breadcrumb = styled.div`
  min-width: 0;
  p { margin: 0; color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; }
  strong { display: block; margin: 1px 0 0; overflow: hidden; font-family: 'CareSync Display', sans-serif; font-size: 1rem; font-weight: 600; letter-spacing: -.025em; text-overflow: ellipsis; white-space: nowrap; }
`;

const HeaderActions = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;
const OrganizationSelect = styled.select`min-height:44px;max-width:190px;padding:0 10px;border:1px solid ${({theme})=>theme.color.controlBorder};border-radius:8px;color:${({theme})=>theme.color.text};background:${({theme})=>theme.color.control};font:inherit;font-size:.75rem;`;

const CommandButton = styled.button`
  display: flex;
  width: clamp(220px, 27vw, 410px);
  min-height: 44px;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border: 1px solid ${({ theme }) => theme.color.controlBorder};
  border-radius: 7px 13px 7px 13px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.control};
  cursor: pointer;
  text-align: left;
  transition: border-color ${({ theme }) => theme.motion.fast} ease, background ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { border-color: ${({ theme }) => theme.color.cyan}; background: ${({ theme }) => theme.color.surfaceHover}; transform: translateY(-1px); }
  svg { width: 18px; height: 18px; }
  span { flex: 1; font-size: .8125rem; }
  kbd { padding: 2px 6px; border: 1px solid ${({ theme }) => theme.color.border}; border-radius: 6px; color: ${({ theme }) => theme.color.textSoft}; font-size: .72rem; }
  @media (max-width: 900px) { width: 44px; padding: 0; justify-content: center; span, kbd { display: none; } }
`;

const DesktopStatus = styled(StatusChip)`
  @media (max-width: 1160px) { display: none; }
`;

const MotionToggle = styled(IconButton)<{ $active: boolean }>`
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border-color: ${({ $active, theme }) => $active ? theme.color.borderStrong : theme.color.border};
  color: ${({ $active, theme }) => $active ? theme.color.cyan : theme.color.textMuted};
  background: ${({ $active, theme }) => $active
    ? `color-mix(in srgb, ${theme.color.cyan} 9%, ${theme.color.control})`
    : theme.color.surfaceStrong};
  box-shadow: ${({ $active, theme }) => $active ? theme.shadow.cyan : 'none'};
`;

const Content = styled.main`
  position: relative;
  /* Do not create a stacking context: route-level fixed dialogs must clear the sticky header. */
  min-width: 0;
  max-width: ${({ theme }) => theme.layout.content};
  margin: 0 auto;
  padding: clamp(20px, 3vw, 44px);

  @media (max-width: ${({ theme }) => theme.breakpoint.mobile}) {
    padding: 18px 14px 92px;
  }
`;

const Overlay = styled.div<{ $visible: boolean }>`
  position: fixed;
  inset: 0;
  z-index: 200;
  pointer-events: ${({ $visible }) => $visible ? 'auto' : 'none'};
  opacity: ${({ $visible }) => $visible ? 1 : 0};
  background: ${({ theme }) => theme.color.overlay};
  transition: opacity 180ms ease;
`;

const PaletteWrap = styled(Overlay)`
  z-index: 500;
  display: grid;
  align-items: start;
  justify-items: center;
  padding: min(14vh, 120px) 18px 20px;
`;

const Palette = styled.div<{ $visible: boolean }>`
  width: min(660px, 100%);
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.color.borderStrong};
  border-radius: 6px;
  opacity: ${({ $visible }) => $visible ? 1 : 0};
  background: ${({ theme }) => theme.color.surface};
  box-shadow: 0 18px 44px rgba(4, 10, 20, .28), inset 0 1px 0 color-mix(in srgb, ${({ theme }) => theme.color.surface} 86%, ${({ theme }) => theme.color.cyan});
  clip-path: polygon(12px 0, calc(100% - 20px) 0, 100% 20px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  transform: translateY(${({ $visible }) => $visible ? '0' : '-14px'}) scale(${({ $visible }) => $visible ? 1 : .98});
  transition: opacity 180ms ease, transform 220ms ${({ theme }) => theme.motion.ease};
`;

const PaletteInput = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  background: ${({ theme }) => theme.color.surfaceStrong};
  svg { width: 21px; color: ${({ theme }) => theme.color.cyan}; }
  input { width: 100%; border: 0; outline: 0; color: ${({ theme }) => theme.color.text}; background: transparent; font-size: .96rem; }
  > button { width: 44px; height: 44px; flex: 0 0 auto; }
`;

const PaletteResults = styled.div`
  max-height: min(56vh, 480px);
  overflow-y: auto;
  padding: 10px;
`;

const PaletteResult = styled.button<{ $selected: boolean }>`
  position: relative;
  display: flex;
  width: 100%;
  min-height: 52px;
  align-items: center;
  gap: 13px;
  padding: 12px;
  border: 1px solid ${({ $selected, theme }) => $selected ? theme.color.borderStrong : 'transparent'};
  border-radius: 6px 12px 6px 12px;
  color: ${({ theme }) => theme.color.text};
  background: ${({ $selected, theme }) => $selected ? `color-mix(in srgb, ${theme.color.surfaceStrong} 88%, ${theme.color.plasma})` : 'transparent'};
  cursor: pointer;
  text-align: left;
  transition: background ${({ theme }) => theme.motion.fast} ease, border-color ${({ theme }) => theme.motion.fast} ease, transform ${({ theme }) => theme.motion.fast} ease;
  &:hover { background: ${({ theme }) => theme.color.surfaceHover}; transform: translateX(1px); }
  svg { width: 20px; color: ${({ $selected, theme }) => $selected ? theme.color.cyan : theme.color.textMuted}; }
  div { flex: 1; }
  strong { display: block; font-size: .82rem; font-weight: 600; }
  small { color: ${({ theme }) => theme.color.textMuted}; font-size: .75rem; }
  span { color: ${({ theme }) => theme.color.textMuted}; font-size: .72rem; text-transform: uppercase; }
`;

function SideRail({ collapsed }: { collapsed: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { mobileOpen, setMobileOpen, toggleCollapsed } = useShellStore();
  const session = useSession();
  const authorizedNavigation = useAuthorizedNavigation();
  const railRef = useRef<HTMLElement>(null);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 720px)').matches);
  const [isCompact, setIsCompact] = useState(() => window.matchMedia('(max-width: 1080px)').matches);
  const [compactExpanded, setCompactExpanded] = useState(false);
  const visuallyCollapsed = isMobile ? false : isCompact ? !compactExpanded : collapsed;
  const userName = session.user?.first_name || 'Account';
  const authenticated = session.status === 'authenticated';
  const sessionChecking = session.status === 'checking';
  const sessionActionLabel = sessionChecking
    ? 'Verifying account'
    : 'Sign out of CareSync';

  const handleSessionAction = () => {
    if (sessionChecking) return;
    if (authenticated) session.logout();
    navigate('/');
    setMobileOpen(false);
  };

  const handleRailToggle = () => {
    if (isCompact && !isMobile) {
      setCompactExpanded((expanded) => !expanded);
      return;
    }
    toggleCollapsed();
  };

  useEffect(() => {
    setMobileOpen(false);
    setCompactExpanded(false);
  }, [location.pathname, setMobileOpen]);
  useEffect(() => {
    const mobileQuery = window.matchMedia('(max-width: 720px)');
    const compactQuery = window.matchMedia('(max-width: 1080px)');
    const sync = () => {
      setIsMobile(mobileQuery.matches);
      setIsCompact(compactQuery.matches);
      if (!compactQuery.matches || mobileQuery.matches) setCompactExpanded(false);
    };
    sync();
    mobileQuery.addEventListener('change', sync);
    compactQuery.addEventListener('change', sync);
    return () => {
      mobileQuery.removeEventListener('change', sync);
      compactQuery.removeEventListener('change', sync);
    };
  }, []);
  useEffect(() => {
    if (!isMobile || !mobileOpen) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const shellMain = document.getElementById('shell-main') as (HTMLElement & { inert: boolean }) | null;
    const previousAriaHidden = shellMain?.getAttribute('aria-hidden');
    document.body.style.overflow = 'hidden';
    if (shellMain) {
      shellMain.inert = true;
      shellMain.setAttribute('aria-hidden', 'true');
    }
    requestAnimationFrame(() => railRef.current?.querySelector<HTMLElement>('a[href]')?.focus());
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      if (shellMain) {
        shellMain.inert = false;
        if (previousAriaHidden == null) shellMain.removeAttribute('aria-hidden');
        else shellMain.setAttribute('aria-hidden', previousAriaHidden);
      }
      window.removeEventListener('keydown', closeOnEscape);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [isMobile, mobileOpen, setMobileOpen]);

  const renderItem = (item: NavigationItem) => {
    const active = location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
    return (
      <NavLink key={item.id} to={item.path} onClick={() => setMobileOpen(false)} aria-current={active ? 'page' : undefined} title={visuallyCollapsed ? item.label : undefined}>
        <NavItem $active={active} $collapsed={visuallyCollapsed}>
          <item.icon aria-hidden="true" />
          <NavCopy $hidden={visuallyCollapsed}>
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </NavCopy>
        </NavItem>
      </NavLink>
    );
  };

  return (
    <>
      {mobileOpen && <Overlay $visible onClick={() => setMobileOpen(false)} aria-hidden="true" />}
      {(!isMobile || mobileOpen) && <Rail
        ref={railRef}
        data-shell-background
        $collapsed={visuallyCollapsed}
        $mobileOpen={mobileOpen}
        role={isMobile ? 'dialog' : 'complementary'}
        aria-modal={isMobile && mobileOpen ? true : undefined}
        aria-label="Primary navigation"
        onKeyDown={(event) => {
          if (!isMobile || event.key !== 'Tab') return;
          const focusable = [...(railRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)') || [])];
          if (focusable.length === 0) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <Brand $collapsed={visuallyCollapsed}>
          <CareSyncMark size={43} />
          <BrandCopy $hidden={visuallyCollapsed}>
            <strong>CareSync</strong>
            <span>Daycare operations</span>
          </BrandCopy>
          <MobileClose onClick={() => setMobileOpen(false)} aria-label="Close navigation">
            <XMarkIcon aria-hidden="true" />
          </MobileClose>
        </Brand>
        <NavScroll>
          {authorizedNavigation.groups.map((group) => (
            <Group key={group.label}>
              <GroupLabel $hidden={visuallyCollapsed}>{group.label}</GroupLabel>
              {group.items.map(renderItem)}
            </Group>
          ))}
        </NavScroll>
        <UtilityArea>{authorizedNavigation.utility.map(renderItem)}</UtilityArea>
        <RailToggleArea $collapsed={visuallyCollapsed}>
          <RailCollapseButton
            onClick={handleRailToggle}
            aria-label={visuallyCollapsed ? 'Expand navigation labels' : 'Collapse navigation labels'}
            title={visuallyCollapsed ? 'Expand navigation labels' : 'Collapse navigation labels'}
          >
            {visuallyCollapsed
              ? <ChevronDoubleRightIcon aria-hidden="true" />
              : <ChevronDoubleLeftIcon aria-hidden="true" />}
          </RailCollapseButton>
        </RailToggleArea>
        <Profile $collapsed={visuallyCollapsed}>
          <ProfileIdentity $hidden={visuallyCollapsed}>
            <Avatar aria-hidden="true">{userName.slice(0, 2).toUpperCase()}</Avatar>
            <ProfileCopy $hidden={false}>
              <strong>{userName}</strong>
              <span>{sessionChecking ? 'Verifying account…' : session.user?.role?.name || 'Workspace member'}</span>
            </ProfileCopy>
          </ProfileIdentity>
          <ProfileSignOutButton
            type="button"
            onClick={handleSessionAction}
            disabled={sessionChecking}
            aria-label={sessionActionLabel}
            title={sessionActionLabel}
          >
            <ArrowRightOnRectangleIcon aria-hidden="true" />
          </ProfileSignOutButton>
        </Profile>
      </Rail>}
    </>
  );
}

function TopBar() {
  const location = useLocation();
  const session = useSession();
  const authorizedNavigation = useAuthorizedNavigation();
  const item = findNavigationItem(location.pathname, authorizedNavigation.all);
  const { setMobileOpen, setCommandOpen } = useShellStore();
  const { mode: motionMode, resolvedMode, setMotionMode } = useMotion();
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [healthCheckedAt, setHealthCheckedAt] = useState<Date | null>(null);
  const realtimeState = useRealtimeState();
  const motionExplicitlyOff = motionMode === 'off';
  const motionActive = resolvedMode === 'full';
  const motionToggleLabel = motionExplicitlyOff
    ? 'Workspace motion is off. Use the system motion preference'
    : resolvedMode === 'reduced'
      ? 'System reduced motion is active. Turn workspace motion off explicitly'
      : 'Workspace motion is active. Turn off workspace motion';
  const healthCheckedLabel = healthCheckedAt?.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const healthCopy = healthy === null ? 'Checking core' : !healthy ? 'Check failed' : realtimeState === 'connected' ? 'Live updates' : realtimeState === 'reconnecting' || realtimeState === 'connecting' ? 'Sync reconnecting' : 'Connected';
  const healthTitle = healthy === null
    ? healthCheckedLabel ? `Rechecking core connectivity. Last checked at ${healthCheckedLabel}.` : 'Checking core and database connectivity.'
    : `${healthy ? `Core and database connectivity passed; realtime is ${realtimeState}` : 'Core or database connectivity did not pass'} at ${healthCheckedLabel || 'the latest check'}. Rechecks and refreshes canonical page data when this window regains focus.`;

  useEffect(() => {
    let controller: AbortController | null = null;
    const checkHealth = () => {
      controller?.abort();
      controller = new AbortController();
      const current = controller;
      setHealthy(null);
      api.health(current.signal)
        .then((health) => {
          if (current.signal.aborted) return;
          setHealthy(health.status === 'ok' && health.database.connected);
          setHealthCheckedAt(new Date());
        })
        .catch(() => {
          if (current.signal.aborted) return;
          setHealthy(false);
          setHealthCheckedAt(new Date());
        });
    };
    checkHealth();
    window.addEventListener('focus', checkHealth);
    return () => {
      controller?.abort();
      window.removeEventListener('focus', checkHealth);
    };
  }, []);

  return (
    <Header>
      <HeaderLeft>
        <MobileMenu onClick={() => setMobileOpen(true)} aria-label="Open navigation">
          <Bars3BottomLeftIcon aria-hidden="true" />
        </MobileMenu>
        <Breadcrumb>
          <p>CareSync / {item?.id || 'workspace'}</p>
          <strong>{item?.label || 'Workspace'}</strong>
        </Breadcrumb>
      </HeaderLeft>
      <HeaderActions>
        {session.organizationChoices.length > 1 && <OrganizationSelect aria-label="Active organization" disabled={session.organizationSwitching} value={session.user?.organization_id || ''} onChange={(event) => void session.switchOrganization(event.target.value).catch(() => undefined)}>{session.organizationChoices.map((choice)=><option key={choice.organization_id} value={choice.organization_id}>{choice.organization_name}</option>)}</OrganizationSelect>}
        <NotificationInbox />
        <DesktopStatus
          $tone={healthy === null ? 'neutral' : healthy && realtimeState === 'connected' ? 'success' : 'warning'}
          role="status"
          aria-live="polite"
          title={healthTitle}
        >
          {healthCopy}
        </DesktopStatus>
        <MotionToggle
          $active={motionActive}
          type="button"
          onClick={() => setMotionMode(motionExplicitlyOff ? 'system' : 'off')}
          aria-pressed={motionExplicitlyOff}
          aria-label={motionToggleLabel}
          title={motionToggleLabel}
          data-effective-motion={resolvedMode}
        >
          <SparklesIcon aria-hidden="true" />
        </MotionToggle>
        <CommandButton
          onClick={() => {
            setMobileOpen(false);
            setCommandOpen(true);
          }}
          aria-label="Open page navigation"
        >
          <MagnifyingGlassIcon aria-hidden="true" />
          <span>Go to a page…</span>
          <kbd>⌘ K</kbd>
        </CommandButton>
      </HeaderActions>
    </Header>
  );
}

function CommandPalette() {
  const { commandOpen, setCommandOpen, setMobileOpen } = useShellStore();
  const navigate = useNavigate();
  const authorizedNavigation = useAuthorizedNavigation();
  const inputRef = useRef<HTMLInputElement>(null);
  const paletteRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const results = useMemo(() => {
    return searchNavigation(query, authorizedNavigation.all);
  }, [authorizedNavigation.all, query]);
  const activeOptionId = results[selected] ? `command-option-${results[selected].id}` : undefined;

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (commandOpen) {
          setCommandOpen(false);
        } else {
          setMobileOpen(false);
          setCommandOpen(true);
        }
      }
      if (event.key === 'Escape') setCommandOpen(false);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [commandOpen, setCommandOpen, setMobileOpen]);

  useEffect(() => {
    if (commandOpen) {
      const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const previousOverflow = document.body.style.overflow;
      const background = [...document.querySelectorAll<HTMLElement>('[data-shell-background]')].map((element) => ({
        element: element as HTMLElement & { inert: boolean },
        inert: (element as HTMLElement & { inert: boolean }).inert,
        ariaHidden: element.getAttribute('aria-hidden'),
      }));
      document.body.style.overflow = 'hidden';
      setQuery('');
      setSelected(0);
      inputRef.current?.focus();
      background.forEach(({ element }) => {
        element.inert = true;
        element.setAttribute('aria-hidden', 'true');
      });
      return () => {
        document.body.style.overflow = previousOverflow;
        background.forEach(({ element, inert, ariaHidden }) => {
          element.inert = inert;
          if (ariaHidden == null) element.removeAttribute('aria-hidden');
          else element.setAttribute('aria-hidden', ariaHidden);
        });
        if (previousFocus?.isConnected) previousFocus.focus();
      };
    }
  }, [commandOpen]);

  useEffect(() => setSelected(0), [query]);

  const choose = (path: string) => {
    navigate(path);
    setCommandOpen(false);
  };

  if (!commandOpen) return null;

  return (
    <PaletteWrap $visible={commandOpen} onMouseDown={(event) => event.target === event.currentTarget && setCommandOpen(false)}>
      <Palette
        ref={paletteRef}
        $visible={commandOpen}
        role="dialog"
        aria-modal="true"
        aria-label="Page navigation"
        onKeyDown={(event) => {
          if (event.key !== 'Tab') return;
          const focusable = [...(paletteRef.current?.querySelectorAll<HTMLElement>('input:not(:disabled):not([tabindex="-1"]), button:not(:disabled):not([tabindex="-1"]), [href]:not([tabindex="-1"])') || [])];
          if (focusable.length === 0) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <PaletteInput>
          <CommandLineIcon aria-hidden="true" />
          <input
            ref={inputRef}
            role="combobox"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown' && results.length > 0) { event.preventDefault(); setSelected((value) => Math.min(value + 1, results.length - 1)); }
              if (event.key === 'ArrowUp' && results.length > 0) { event.preventDefault(); setSelected((value) => Math.max(value - 1, 0)); }
              if (event.key === 'Enter' && results[selected]) choose(results[selected].path);
            }}
            placeholder="Where do you want to go?"
            aria-label="Find a CareSync page"
            aria-expanded="true"
            aria-autocomplete="list"
            aria-controls="command-results"
            aria-activedescendant={activeOptionId}
          />
          <IconButton onClick={() => setCommandOpen(false)} aria-label="Close page navigation">
            <XMarkIcon aria-hidden="true" />
          </IconButton>
        </PaletteInput>
        <PaletteResults id="command-results" role="listbox" aria-label="CareSync pages">
          {results.map((item, index) => (
            <PaletteResult
              key={item.id}
              id={`command-option-${item.id}`}
              role="option"
              tabIndex={-1}
              aria-selected={selected === index}
              $selected={selected === index}
              onMouseEnter={() => setSelected(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(item.path)}
            >
              <item.icon aria-hidden="true" />
              <div><strong>{item.label}</strong><small>{item.description}</small></div>
              <span>{item.status}</span>
            </PaletteResult>
          ))}
          {results.length === 0 && <PaletteResult as="div" role="status" $selected={false}><SparklesIcon aria-hidden="true" /><div><strong>No matching page</strong><small>Try a broader search.</small></div></PaletteResult>}
        </PaletteResults>
      </Palette>
    </PaletteWrap>
  );
}

export function AppShell() {
  const { collapsed } = useShellStore();
  return (
    <Shell $collapsed={collapsed}>
      <SkipLink href="#main-content" data-shell-background>Skip to main content</SkipLink>
      <SideRail collapsed={collapsed} />
      <Main id="shell-main" data-shell-background>
        <WorkspaceMotionLayer />
        <TopBar />
        <ChildcareCommandRecoverySurface />
        <Content id="main-content" tabIndex={-1}>
          <Outlet />
        </Content>
      </Main>
      <CommandPalette />
    </Shell>
  );
}
