import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  api,
  ApiError,
  clearSessionToken,
  getSessionToken,
  saveSessionToken,
  saveSelectedOrganizationId,
  getSelectedOrganizationId,
  clearSelectedOrganizationId,
  type OrganizationChoice,
  SELECTED_ORGANIZATION_KEY,
  SESSION_TOKEN_KEY,
  type ApiUser,
  type OrganizationRecord,
  AUTHORIZATION_RECHECK_EVENT,
} from '../api/client';
import { staffApi } from '../features/staff/staffApi';
import {
  isOrganizationSessionBoundaryError,
  reconcileOrganizationSessionFacts,
} from './organizationSessionRefresh';

type SessionStatus = 'checking' | 'anonymous' | 'authenticated' | 'unavailable';

interface SessionContextValue {
  status: SessionStatus;
  user: ApiUser | null;
  organization: OrganizationRecord | null;
  organizationUnavailable: boolean;
  organizationChoices: OrganizationChoice[];
  organizationSwitching: boolean;
  login: (email: string, password: string, organizationId?: string) => Promise<void>;
  register: (input: { email: string; password: string; firstName: string; lastName: string; organizationName?: string }) => Promise<void>;
  activateStaff: (token: string, password: string) => Promise<void>;
  logout: () => void;
  retry: () => void;
  switchOrganization: (organizationId: string) => Promise<void>;
  refreshOrganizationFacts: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('checking');
  const [user, setUser] = useState<ApiUser | null>(null);
  const [organization, setOrganization] = useState<OrganizationRecord | null>(null);
  const [organizationUnavailable, setOrganizationUnavailable] = useState(false);
  const [organizationChoices, setOrganizationChoices] = useState<OrganizationChoice[]>([]);
  const [organizationSwitching, setOrganizationSwitching] = useState(false);
  const switchGeneration = useRef(0);
  const confirmedContext = useRef<{ user: ApiUser; organization: OrganizationRecord } | null>(null);
  const organizationRequestVersion = useRef(0);
  const organizationFactsRefresh = useRef<{
    organizationId: string;
    promise: Promise<void>;
  } | null>(null);
  const authorizationRecheckActive = useRef(false);
  const [bootstrapVersion, setBootstrapVersion] = useState(0);
  const activeSession = useRef({ status, user, organization, organizationUnavailable });
  activeSession.current = { status, user, organization, organizationUnavailable };

  const loadOrganization = useCallback(async (signal?: AbortSignal) => {
    const requestVersion = ++organizationRequestVersion.current;
    try {
      const nextOrganization = await api.organization(signal);
      if (requestVersion === organizationRequestVersion.current) {
        setOrganization(nextOrganization);
        setOrganizationUnavailable(false);
      }
    } catch {
      if (!signal?.aborted && requestVersion === organizationRequestVersion.current) {
        setOrganization(null);
        setOrganizationUnavailable(true);
      }
    }
  }, []);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      setStatus('anonymous');
      return;
    }
    const controller = new AbortController();
    void (async () => {
      try {
        const choices = await api.organizations(controller.signal);
        if (controller.signal.aborted) return;
        setOrganizationChoices(choices.organizations);
        const selected = getSelectedOrganizationId();
        const valid = choices.organizations.some((item) => item.organization_id === selected);
        if (!valid) {
          clearSelectedOrganizationId();
          if (choices.organizations.length === 1) saveSelectedOrganizationId(choices.organizations[0].organization_id);
          else if (choices.organizations.length > 1) { setStatus('anonymous'); return; }
        }
        const identity = await api.me(controller.signal);
        if (controller.signal.aborted) return;
        setUser(identity);
        if (identity.organization_id) saveSelectedOrganizationId(identity.organization_id);
        setStatus('authenticated');
        void loadOrganization(controller.signal);
      } catch (caught) {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 403)) {
          clearSessionToken();
          setUser(null);
          setOrganization(null);
          setStatus('anonymous');
        } else {
          setStatus('unavailable');
        }
      }
    })();
    return () => controller.abort();
  }, [loadOrganization, bootstrapVersion]);

  const login = useCallback(async (email: string, password: string, organizationId?: string) => {
    organizationRequestVersion.current += 1;
    setOrganizationChoices([]);
    const result = await api.login(email, password, organizationId);
    saveSessionToken(result.access_token);
    if (result.user.organization_id) saveSelectedOrganizationId(result.user.organization_id);
    setUser(result.user);
    setStatus('authenticated');
    const choices = await api.organizations(); setOrganizationChoices(choices.organizations);
    await loadOrganization();
  }, [loadOrganization]);

  const register = useCallback(async (input: { email: string; password: string; firstName: string; lastName: string; organizationName?: string }) => {
    organizationRequestVersion.current += 1;
    const result = await api.register({
      email: input.email.trim().toLowerCase(),
      password: input.password,
      first_name: input.firstName.trim(),
      last_name: input.lastName.trim(),
      ...(input.organizationName?.trim() ? { organization_name: input.organizationName.trim() } : {}),
    });
    saveSessionToken(result.access_token);
    if (result.user.organization_id) saveSelectedOrganizationId(result.user.organization_id);
    setUser(result.user);
    setStatus('authenticated');
    const choices = await api.organizations(); setOrganizationChoices(choices.organizations);
    await loadOrganization();
  }, [loadOrganization]);

  const activateStaff = useCallback(async (token: string, password: string) => {
    organizationRequestVersion.current += 1;
    const result = await staffApi.activate(token, password);
    saveSessionToken(result.access_token);
    if (result.user.organization_id) saveSelectedOrganizationId(result.user.organization_id);
    setUser(result.user);
    setStatus('authenticated');
    const choices = await api.organizations(); setOrganizationChoices(choices.organizations);
    await loadOrganization();
  }, [loadOrganization]);

  const logout = useCallback(() => {
    organizationRequestVersion.current += 1;
    organizationFactsRefresh.current = null;
    clearSessionToken();
    setUser(null);
    setOrganization(null);
    setOrganizationUnavailable(false);
    setOrganizationChoices([]);
    setStatus('anonymous');
  }, []);

  const refreshOrganizationFacts = useCallback((): Promise<void> => {
    const snapshot = activeSession.current;
    if (snapshot.status !== 'authenticated') return Promise.resolve();
    if (
      !snapshot.user
      || !snapshot.organization
      || snapshot.organizationUnavailable
      || !snapshot.user.organization_id
      || snapshot.user.organization_id !== snapshot.organization.id
    ) {
      const error = new ApiError(403, 'The authenticated organization boundary is not confirmed.');
      logout();
      return Promise.reject(error);
    }

    const expectedOrganizationId = snapshot.organization.id;
    if (getSelectedOrganizationId() !== expectedOrganizationId) {
      const error = new ApiError(403, 'The selected organization no longer matches the authenticated boundary.');
      logout();
      return Promise.reject(error);
    }
    const pending = organizationFactsRefresh.current;
    if (pending?.organizationId === expectedOrganizationId) return pending.promise;

    const requestVersion = ++organizationRequestVersion.current;
    const entry: { organizationId: string; promise: Promise<void> } = {
      organizationId: expectedOrganizationId,
      promise: Promise.resolve(),
    };
    entry.promise = Promise.all([api.organizations(), api.organization(), api.me()])
      .then(([choices, refreshedOrganization, refreshedUser]) => {
        if (requestVersion !== organizationRequestVersion.current) return;
        const current = activeSession.current;
        if (current.status !== 'authenticated') return;
        if (
          current.user?.organization_id !== expectedOrganizationId
          || current.organization?.id !== expectedOrganizationId
          || refreshedUser.organization_id !== expectedOrganizationId
          || getSelectedOrganizationId() !== expectedOrganizationId
        ) throw new ApiError(403, 'The organization boundary changed during canonical refresh.');
        const reconciled = reconcileOrganizationSessionFacts(
          refreshedUser,
          current.organization,
          choices.organizations,
          refreshedOrganization,
        );
        setUser(refreshedUser);
        setOrganizationChoices(reconciled.organizationChoices);
        setOrganization(reconciled.organization);
        setOrganizationUnavailable(false);
        confirmedContext.current = {
          user: refreshedUser,
          organization: reconciled.organization,
        };
      })
      .catch((caught) => {
        if (
          requestVersion === organizationRequestVersion.current
          && isOrganizationSessionBoundaryError(caught)
        ) logout();
        throw caught;
      })
      .finally(() => {
        if (organizationFactsRefresh.current === entry) organizationFactsRefresh.current = null;
      });
    organizationFactsRefresh.current = entry;
    return entry.promise;
  }, [logout]);

  const retry = useCallback(() => {
    if (!getSessionToken()) {
      setStatus('anonymous');
      return;
    }
    organizationRequestVersion.current += 1;
    organizationFactsRefresh.current = null;
    setUser(null);
    setOrganization(null);
    setOrganizationUnavailable(false);
    setStatus('checking');
    setBootstrapVersion((value) => value + 1);
  }, []);

  const switchOrganization = useCallback(async (organizationId: string) => {
    if (!organizationChoices.some((item) => item.organization_id === organizationId)) throw new ApiError(403, 'That organization is not available to this identity.');
    const generation = ++switchGeneration.current;
    organizationRequestVersion.current += 1;
    organizationFactsRefresh.current = null;
    const previous = confirmedContext.current;
    setOrganizationSwitching(true); setStatus('checking'); setUser(null); setOrganization(null);
    saveSelectedOrganizationId(organizationId);
    try {
      const identity = await api.me(); if (generation !== switchGeneration.current) return;
      if (identity.organization_id !== organizationId) throw new ApiError(403, 'The server did not confirm the selected organization.');
      const confirmedOrganization = await api.organization(); if (generation !== switchGeneration.current) return;
      if (confirmedOrganization.id !== organizationId) throw new ApiError(403, 'The organization response crossed the selected boundary.');
      confirmedContext.current = { user: identity, organization: confirmedOrganization }; setUser(identity); setOrganization(confirmedOrganization); setStatus('authenticated');
    } catch (caught) {
      if (generation !== switchGeneration.current) return;
      if (caught instanceof ApiError && [401, 403, 409].includes(caught.status)) { logout(); throw caught; }
      if (previous) { saveSelectedOrganizationId(previous.organization.id); setUser(previous.user); setOrganization(previous.organization); setStatus('authenticated'); }
      else { clearSelectedOrganizationId(); setStatus('unavailable'); }
      throw caught;
    } finally { if (generation === switchGeneration.current) setOrganizationSwitching(false); }
  }, [logout, organizationChoices]);

  useEffect(() => { if (status === 'authenticated' && user && organization && user.organization_id === organization.id) confirmedContext.current = { user, organization }; if (status === 'anonymous') confirmedContext.current = null; }, [organization, status, user]);

  useEffect(() => {
    const handleUnauthorized = () => logout();
    const handleAuthorizationRecheck = async () => {
      if (authorizationRecheckActive.current || !getSessionToken()) return;
      authorizationRecheckActive.current = true;
      organizationRequestVersion.current += 1;
      setUser(null); setOrganization(null); setOrganizationUnavailable(false); setStatus('checking');
      try {
        const identity = await api.me();
        const confirmedOrganization = await api.organization();
        if (identity.organization_id !== confirmedOrganization.id) throw new ApiError(403, 'The active organization context is no longer valid.');
        setUser(identity); setOrganization(confirmedOrganization); setStatus('authenticated');
      } catch (caught) {
        if (caught instanceof ApiError && [401, 403, 409].includes(caught.status)) logout();
        else setStatus('unavailable');
      } finally { authorizationRecheckActive.current = false; }
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key === SELECTED_ORGANIZATION_KEY) { if (getSessionToken()) retry(); else logout(); return; }
      if (event.key !== SESSION_TOKEN_KEY) return;
      if (event.newValue) retry();
      else logout();
    };
    window.addEventListener('caresync-redesign:unauthorized', handleUnauthorized);
    window.addEventListener(AUTHORIZATION_RECHECK_EVENT, handleAuthorizationRecheck);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener('caresync-redesign:unauthorized', handleUnauthorized);
      window.removeEventListener(AUTHORIZATION_RECHECK_EVENT, handleAuthorizationRecheck);
      window.removeEventListener('storage', handleStorage);
    };
  }, [logout, retry]);

  const value = useMemo<SessionContextValue>(() => ({
    status,
    user,
    organization,
    organizationUnavailable,
    organizationChoices,
    organizationSwitching,
    login,
    register,
    activateStaff,
    logout,
    retry,
    switchOrganization,
    refreshOrganizationFacts,
  }), [status, user, organization, organizationUnavailable, organizationChoices, organizationSwitching, login, register, activateStaff, logout, retry, switchOrganization, refreshOrganizationFacts]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used within SessionProvider');
  return value;
}
