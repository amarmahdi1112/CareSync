import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BellIcon, CheckIcon, Cog6ToothIcon, ComputerDesktopIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { IconButton } from '../../components/ui/Primitives';
import { useShellStore } from '../../state/useShellStore';
import { notificationsApi, type NotificationItem, type NotificationPreferences } from './notificationsApi';
import { useSession } from '../../auth/SessionContext';
import { notificationOrganizationTarget, safeNotificationActionPath } from './notificationNavigation';
import {
  canUseDesktopNotifications,
  desktopNotificationCopy,
  desktopPreferenceKey,
  organizationSafeToastCopy,
  readSeenNotificationIds,
  seenNotificationKey,
  shouldDeliverActiveAlert,
  shouldShowDesktopNotification,
  writeSeenNotificationIds,
} from './notificationDelivery';
import { subscribeNotificationEvents } from './notificationEvents';
import {
  fetchRoomExceptionActionTarget,
  roomExceptionTargetPath,
} from '../rooms/roomSafetyApi';

const Wrap = styled.div`position: relative;`;
const Trigger = styled(IconButton)`position: relative; width: 44px; height: 44px;`;
const Badge = styled.span`position:absolute; top:-4px; right:-4px; min-width:20px; height:20px; display:grid; place-items:center; padding:0 5px; border-radius:999px; color:#06111c; background:${({theme})=>theme.color.amber}; font-size:.68rem; font-weight:700;`;
const Panel = styled.section`position:absolute; top:52px; right:0; width:min(420px,calc(100vw - 24px)); max-height:min(680px,calc(100vh - 90px)); display:flex; flex-direction:column; border:1px solid ${({theme})=>theme.color.borderStrong}; border-radius:12px; background:${({theme})=>theme.color.canvasElevated}; box-shadow:${({theme})=>theme.shadow.panel}; overflow:hidden; z-index:500;`;
const Head = styled.header`display:flex; align-items:center; justify-content:space-between; gap:12px; padding:14px 16px; border-bottom:1px solid ${({theme})=>theme.color.border}; h2{margin:0;font-size:1rem;font-weight:600} button{color:${({theme})=>theme.color.cyan};background:none;border:0;cursor:pointer}`;
const List = styled.div`overflow:auto;`;
const Item = styled.button<{ $read: boolean }>`display:block;width:100%;padding:14px 16px;border:0;border-bottom:1px solid ${({theme})=>theme.color.border};color:inherit;background:${({$read,theme})=>$read?'transparent':`color-mix(in srgb, ${theme.color.cyan} 7%, ${theme.color.surface})`};text-align:left;cursor:pointer;strong,span,small{display:block}strong{font-size:.86rem;font-weight:600}span{margin-top:5px;color:${({theme})=>theme.color.textSoft};font-size:.78rem;line-height:1.45}small{margin-top:7px;color:${({theme})=>theme.color.textMuted};font-size:.68rem}`;
const Empty = styled.p`padding:28px 18px;color:${({theme})=>theme.color.textMuted};text-align:center;`;
const ErrorBox = styled.p`margin:10px 14px;padding:10px;border:1px solid ${({theme})=>theme.color.coral};border-radius:8px;color:${({theme})=>theme.color.coral};font-size:.78rem;`;
const Preferences = styled.div`padding:12px 16px;border-top:1px solid ${({theme})=>theme.color.border};label{display:flex;justify-content:space-between;gap:12px;padding:7px 0;color:${({theme})=>theme.color.textSoft};font-size:.78rem}small{display:block;color:${({theme})=>theme.color.textMuted};font-size:.7rem;line-height:1.45}`;
const DesktopButton = styled.button`display:flex;min-height:44px;width:100%;align-items:center;justify-content:center;gap:8px;margin-top:8px;border:1px solid ${({theme})=>theme.color.controlBorder}!important;border-radius:8px;color:${({theme})=>theme.color.cyan};background:${({theme})=>theme.color.control}!important;font:inherit;font-size:.76rem;svg{width:17px}`;
const ToastRegion = styled.section`position:fixed;right:18px;bottom:18px;z-index:800;display:grid;width:min(390px,calc(100vw - 36px));gap:10px;pointer-events:none;`;
const Toast = styled.article<{ $critical: boolean }>`pointer-events:auto;padding:14px;border:1px solid ${({$critical,theme})=>$critical?theme.color.coral:theme.color.borderStrong};border-radius:10px 15px 10px 10px;background:${({theme})=>theme.color.canvasElevated};box-shadow:${({theme})=>theme.shadow.panel};h3{margin:0 28px 4px 0;font-size:.84rem;font-weight:650}p{margin:0;color:${({theme})=>theme.color.textSoft};font-size:.75rem;line-height:1.45}footer{display:flex;justify-content:flex-end;gap:6px;margin-top:10px}button{min-height:40px;padding:0 11px;border:1px solid ${({theme})=>theme.color.controlBorder};border-radius:8px;color:${({theme})=>theme.color.textSoft};background:${({theme})=>theme.color.control};font:inherit;font-size:.72rem;cursor:pointer}button:last-child{color:${({theme})=>theme.color.cyan}}`;

interface ToastItem { notification: NotificationItem; title: string; body: string }

export function NotificationInbox() {
  const navigate = useNavigate();
  const session = useSession();
  const { notificationsOpen, setNotificationsOpen } = useShellStore();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState('');
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [showPreferences, setShowPreferences] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [desktopEnabled, setDesktopEnabled] = useState(false);
  const initialized = useRef(false);
  const known = useRef(new Set<string>());
  const loadLatest = useRef<(signal?: AbortSignal) => Promise<void>>(async () => undefined);
  const organizationId = session.user?.organization_id || '';
  const userId = session.user?.id || '';
  const desktopAvailable = canUseDesktopNotifications(
    typeof window !== 'undefined' && window.isSecureContext,
    typeof Notification === 'undefined' ? undefined : Notification,
  );
  const desktopKey = userId && organizationId ? desktopPreferenceKey(userId, organizationId) : '';
  const seenKey = userId ? seenNotificationKey(userId) : '';

  const deliver = useCallback((fresh: NotificationItem[], activePreferences: NotificationPreferences) => {
    if (!organizationId || !userId || fresh.length === 0) return;
    const seen = readSeenNotificationIds(localStorage, seenKey);
    const unseen = fresh.filter((item) => !known.current.has(item.id) && !seen.has(item.id));
    fresh.forEach((item) => known.current.add(item.id));
    if (!initialized.current) {
      initialized.current = true;
      writeSeenNotificationIds(localStorage, seenKey, new Set([...seen, ...fresh.map((item) => item.id)]));
      return;
    }
    if (!unseen.length) return;
    writeSeenNotificationIds(localStorage, seenKey, new Set([...seen, ...unseen.map((item) => item.id)]));
    const active = unseen.filter((item) => shouldDeliverActiveAlert(item, activePreferences));
    if (!active.length) return;
    const next = active.slice(0, 4).map((notification) => {
      const choice = session.organizationChoices.find((row) => row.organization_id === notification.organization_id);
      return { notification, ...organizationSafeToastCopy(notification, organizationId, choice?.organization_name) };
    });
    setToasts((current) => [...next, ...current.filter((toast) => !active.some((item) => item.id === toast.notification.id))].slice(0, 4));
    if (desktopEnabled && desktopAvailable && Notification.permission === 'granted' && shouldShowDesktopNotification(document.visibilityState, document.hasFocus())) {
      active.forEach((item) => {
        try {
          const copy = desktopNotificationCopy(item);
          const desktop = new Notification(copy.title, { body: copy.body, tag: `caresync-${item.id}` });
          desktop.onclick = () => { window.focus(); setNotificationsOpen(true); desktop.close(); };
        } catch { /* Browser delivery failure must not block the private event cursor. */ }
      });
    }
  }, [desktopAvailable, desktopEnabled, organizationId, seenKey, session.organizationChoices, setNotificationsOpen, userId]);

  const load = useCallback(async (signal?: AbortSignal) => {
    const [page, summary, nextPreferences] = await Promise.all([notificationsApi.list(signal), notificationsApi.summary(signal), notificationsApi.preferences(signal)]);
    deliver(page.items, nextPreferences);
    setItems(page.items);
    setUnread(summary.unread_total);
    setPreferences(nextPreferences);
    setError('');
  }, [deliver]);
  loadLatest.current = load;

  useEffect(() => {
    setItems([]); setUnread(0); setPreferences(null); setToasts([]);
    initialized.current = false; known.current = new Set();
    setDesktopEnabled(Boolean(desktopKey && localStorage.getItem(desktopKey) === 'enabled' && desktopAvailable && Notification.permission === 'granted'));
  }, [desktopAvailable, desktopKey, organizationId]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Notifications are unavailable.'); }); return () => controller.abort(); }, [load]);
  useEffect(() => {
    if (!organizationId) return;
    let pending = false;
    const poll = () => {
      if (pending || document.visibilityState === 'hidden') return;
      pending = true;
      void load().catch((caught) => setError(caught instanceof Error ? caught.message : 'Notifications are unavailable.')).finally(() => { pending = false; });
    };
    const visible = () => { if (document.visibilityState !== 'hidden') poll(); };
    const interval = window.setInterval(poll, 60_000);
    window.addEventListener('focus', poll);
    window.addEventListener('online', poll);
    document.addEventListener('visibilitychange', visible);
    return () => { window.clearInterval(interval); window.removeEventListener('focus', poll); window.removeEventListener('online', poll); document.removeEventListener('visibilitychange', visible); };
  }, [load, organizationId]);
  useEffect(() => {
    if (!userId) return;
    const subscription = subscribeNotificationEvents({ userId, onInvalidate: async (event) => {
      if (event.type === 'reset_required' || ['notification.created', 'notification.read', 'notification.read_all'].includes(event.type)) await loadLatest.current();
      if (event.type === 'notification.preferences_updated') setPreferences(await notificationsApi.preferences());
    } });
    return () => subscription.close();
  }, [userId]);
  useEffect(() => { if (!notificationsOpen) return; const controller = new AbortController(); void load(controller.signal).catch((caught) => { if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Notifications are unavailable.'); }); return () => controller.abort(); }, [notificationsOpen, load]);

  const open = async (item: NotificationItem) => {
    setError('');
    try {
      let path = safeNotificationActionPath(item.action);
      if (item.action && !path) throw new Error('This notification contains an unsafe or unsupported destination.');
      const target = notificationOrganizationTarget(item.organization_id, session.user?.organization_id || null, session.organizationChoices);
      if (target == null) throw new Error('This notification belongs to an organization that is no longer available.');
      if (target !== 'current') {
        if (!window.confirm(`Switch to ${target.organization_name} to open this notification?`)) return;
        await session.switchOrganization(target.organization_id);
      }
      if (
        item.action?.path === '/rooms'
        && item.action.entity_type === 'room_operational_exception'
      ) {
        const targetOrganizationId =
          item.organization_id || session.user?.organization_id || '';
        if (!targetOrganizationId)
          throw new Error('The operational notification organization is unavailable.');
        const actionTarget = await fetchRoomExceptionActionTarget({
          organizationId: targetOrganizationId,
          exceptionId: item.action.entity_id,
        });
        path = roomExceptionTargetPath(actionTarget);
      }
      if (!item.read_at) {
        const updated = await notificationsApi.read(item.id);
        setItems((current) => current.map((row) => row.id === item.id ? updated : row));
        setUnread((value) => Math.max(0, value - 1));
      }
      setToasts((current) => current.filter((toast) => toast.notification.id !== item.id));
      if (path) { setNotificationsOpen(false); navigate(path); }
      else setNotificationsOpen(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'The notification could not be updated.'); }
  };
  const updatePreference = async (key: 'hiring_enabled'|'credential_enabled'|'assignment_enabled'|'operations_enabled'|'push_enabled', checked: boolean) => { if (!preferences) return; try { setPreferences(await notificationsApi.updatePreferences({ hiring_enabled: preferences.hiring_enabled, credential_enabled: preferences.credential_enabled, assignment_enabled: preferences.assignment_enabled, operations_enabled: preferences.operations_enabled, push_enabled: preferences.push_enabled, [key]: checked })); } catch (caught) { setError(caught instanceof Error ? caught.message : 'Preferences could not be updated.'); } };
  const toggleDesktop = async () => {
    if (!desktopAvailable || !desktopKey) { setError('Desktop notifications require a supported browser on localhost or HTTPS.'); return; }
    if (desktopEnabled) { localStorage.removeItem(desktopKey); setDesktopEnabled(false); return; }
    const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
    if (permission !== 'granted') { localStorage.removeItem(desktopKey); setDesktopEnabled(false); setError(permission === 'denied' ? 'Desktop notifications are blocked in browser settings.' : 'Desktop notifications were not enabled.'); return; }
    localStorage.setItem(desktopKey, 'enabled'); setDesktopEnabled(true); setError('');
  };
  const notificationList = items.length ? items.map((item) => {
    const choice = session.organizationChoices.find((row) => row.organization_id === item.organization_id);
    const copy = organizationSafeToastCopy(item, organizationId, choice?.organization_name);
    return <Item key={item.id} $read={Boolean(item.read_at)} type="button" onClick={() => void open(item)}>
      <strong>{copy.title}</strong><span>{copy.body}</span>
      <small>{item.category}{choice && choice.organization_id !== organizationId ? ` · ${choice.organization_name}` : ''} · {new Date(item.created_at).toLocaleString()}</small>
    </Item>;
  }) : <Empty>No notifications yet.</Empty>;

  const toastRegion = useMemo(() => <ToastRegion aria-label="Recent CareSync updates" aria-live="polite" aria-relevant="additions">
    {toasts.map((toast) => <Toast key={toast.notification.id} $critical={toast.notification.severity === 'critical'} role={toast.notification.severity === 'critical' ? 'alert' : 'status'}>
      <h3>{toast.title}</h3><p>{toast.body}</p><footer><button type="button" onClick={() => setToasts((current) => current.filter((row) => row.notification.id !== toast.notification.id))}>Dismiss</button><button type="button" onClick={() => void open(toast.notification)}>Review securely</button></footer>
    </Toast>)}
  </ToastRegion>, [toasts]);

  return <><Wrap><Trigger type="button" onClick={() => setNotificationsOpen(!notificationsOpen)} aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`} aria-expanded={notificationsOpen}><BellIcon />{unread > 0 && <Badge>{unread > 99 ? '99+' : unread}</Badge>}</Trigger>{notificationsOpen && <Panel aria-label="Notifications"><Head><h2>Notifications</h2><div><button type="button" onClick={() => setShowPreferences((value)=>!value)} aria-label="Notification preferences"><Cog6ToothIcon width={18}/></button>{unread > 0 && <button type="button" onClick={() => void notificationsApi.readAll().then(() => { setItems((current)=>current.map((item)=>({...item,read_at:item.read_at||new Date().toISOString()}))); setUnread(0); }).catch((caught)=>setError(caught instanceof Error?caught.message:'Notifications could not be marked read.'))}><CheckIcon width={18}/> Read all</button>}<IconButton type="button" onClick={()=>setNotificationsOpen(false)} aria-label="Close notifications"><XMarkIcon/></IconButton></div></Head>{error&&<ErrorBox role="alert">{error}</ErrorBox>}{showPreferences&&preferences&&<Preferences>{(['hiring_enabled','credential_enabled','assignment_enabled','operations_enabled'] as const).map((key)=><label key={key}>{key.replace('_enabled','').replace(/^./,(letter)=>letter.toUpperCase())} alerts<input type="checkbox" checked={preferences[key]} onChange={(event)=>void updatePreference(key,event.target.checked)}/></label>)}<label>Registered-device push <input type="checkbox" checked={preferences.push_enabled} onChange={(event)=>void updatePreference('push_enabled',event.target.checked)}/></label><label>System alerts <input type="checkbox" checked disabled/></label><DesktopButton type="button" onClick={() => void toggleDesktop()} aria-pressed={desktopEnabled}><ComputerDesktopIcon />{desktopEnabled ? 'Turn off desktop alerts' : 'Enable private desktop alerts'}</DesktopButton><small>Category switches control new portal, desktop, and registered-device alerts; every item still remains in the secure inbox. System alerts always stay active. Desktop alerts are optional and use generic text only.</small></Preferences>}<List>{notificationList}</List></Panel>}</Wrap>{toastRegion}</>;
}
