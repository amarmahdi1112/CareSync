/* eslint-disable react-refresh/only-export-components */
/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { createContext, useContext, useReducer, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { AuthState, User, Organization } from '../types';
import { api, type ApiUser } from '../api/client';

interface AuthAction {
  type: 'LOGIN' | 'LOGOUT' | 'SET_USER' | 'SET_LOADING' | 'SET_ORGANIZATION';
  payload?: any;
}

interface ExtendedAuthState extends AuthState {
  isLoading: boolean;
  organization: Organization | null;
}

interface AuthContextType {
  state: ExtendedAuthState;
  login: (user: User, token: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
  setOrganization: (org: Organization | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const authReducer = (state: ExtendedAuthState, action: AuthAction): ExtendedAuthState => {
  switch (action.type) {
    case 'LOGIN':
      return {
        ...state,
        user: action.payload.user,
        token: action.payload.token,
        isAuthenticated: true,
        isLoading: false,
      };
    case 'LOGOUT':
      return {
        ...state,
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: false,
        organization: null,
      };
    case 'SET_USER':
      return {
        ...state,
        user: action.payload,
        isAuthenticated: true,
      };
    case 'SET_LOADING':
      return {
        ...state,
        isLoading: action.payload,
      };
    case 'SET_ORGANIZATION':
      return {
        ...state,
        organization: action.payload,
      };
    default:
      return state;
  }
};

// Check for persisted user data
const getPersistedUser = (): User | null => {
  try {
    const userData = localStorage.getItem('user');
    return userData ? JSON.parse(userData) : null;
  } catch {
    return null;
  }
};

const persistedUser = getPersistedUser();
const persistedToken = localStorage.getItem('token');

// Check for persisted organization data
const getPersistedOrganization = (): Organization | null => {
  try {
    const orgData = localStorage.getItem('organization');
    return orgData ? JSON.parse(orgData) : null;
  } catch {
    return null;
  }
};

// Clean up inconsistent state (token without user)
if (persistedToken && !persistedUser) {
  localStorage.removeItem('token');
}

const persistedOrganization = getPersistedOrganization();

// Only authenticated if we have BOTH token AND user
const initialState: ExtendedAuthState = {
  user: persistedUser,
  token: persistedUser ? persistedToken : null,
  isAuthenticated: !!(persistedToken && persistedUser),
  isLoading: Boolean(persistedToken),
  organization: persistedOrganization,
};

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [state, dispatch] = useReducer(authReducer, initialState);

  const mapUser = (user: ApiUser): User => ({
    id: user.id,
    email: user.email,
    firstName: user.first_name,
    lastName: user.last_name,
    role: user.role.name,
    organizationId: user.organization_id || undefined,
  });

  useEffect(() => {
    if (!state.token) {
      dispatch({ type: 'SET_LOADING', payload: false });
      return;
    }
    let cancelled = false;
    Promise.all([api.auth.me(), api.get<Organization>('/organization')])
      .then(([user, organization]) => {
        if (cancelled) return;
        const mapped = mapUser(user);
        localStorage.setItem('user', JSON.stringify(mapped));
        dispatch({ type: 'SET_USER', payload: mapped });
        if (organization) localStorage.setItem('organization', JSON.stringify(organization));
        dispatch({ type: 'SET_ORGANIZATION', payload: organization });
        dispatch({ type: 'SET_LOADING', payload: false });
      })
      .catch(() => {
        if (!cancelled) logout();
      });
    return () => { cancelled = true; };
  }, [state.token]);

  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener('caresync:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('caresync:unauthorized', handleUnauthorized);
  }, []);

  const login = (user: User, token: string) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    dispatch({ type: 'LOGIN', payload: { user, token } });
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('organization');
    dispatch({ type: 'LOGOUT' });
  };

  const setUser = (user: User) => {
    localStorage.setItem('user', JSON.stringify(user));
    dispatch({ type: 'SET_USER', payload: user });
  };

  const setOrganization = (org: Organization | null) => {
    if (org) {
      localStorage.setItem('organization', JSON.stringify(org));
    } else {
      localStorage.removeItem('organization');
    }
    dispatch({ type: 'SET_ORGANIZATION', payload: org });
  };

  return (
    <AuthContext.Provider value={{ state, login, logout, setUser, setOrganization }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
