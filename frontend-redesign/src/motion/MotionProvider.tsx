import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  CARESYNC_MOTION_STORAGE_KEY,
  parseMotionMode,
  resolveMotionPreference,
  type MotionEnvironment,
  type MotionMode,
  type MotionSnapshot,
} from './motionModel';

interface MotionContextValue extends MotionSnapshot {
  setMotionMode: (mode: MotionMode) => void;
}

const MotionContext = createContext<MotionContextValue | null>(null);

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';
const FINE_POINTER_QUERY = '(pointer: fine)';

function safeStoredMode(): MotionMode {
  try {
    return parseMotionMode(window.localStorage.getItem(CARESYNC_MOTION_STORAGE_KEY));
  } catch {
    return 'system';
  }
}

function mediaMatches(query: string): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(query).matches;
}

function documentIsVisible(): boolean {
  return document.visibilityState !== 'hidden';
}

function initialEnvironment(): MotionEnvironment {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return {
      mode: 'system',
      prefersReducedMotion: false,
      documentVisible: true,
      finePointer: false,
    };
  }

  return {
    mode: safeStoredMode(),
    prefersReducedMotion: mediaMatches(REDUCED_MOTION_QUERY),
    documentVisible: documentIsVisible(),
    finePointer: mediaMatches(FINE_POINTER_QUERY),
  };
}

function subscribeToMediaQuery(query: MediaQueryList, listener: () => void): () => void {
  if (typeof query.addEventListener === 'function') {
    query.addEventListener('change', listener);
    return () => query.removeEventListener('change', listener);
  }

  query.addListener(listener);
  return () => query.removeListener(listener);
}

function restoreAttribute(element: HTMLElement, previousValue: string | null): void {
  if (previousValue == null) element.removeAttribute('data-caresync-motion');
  else element.setAttribute('data-caresync-motion', previousValue);
}

export function MotionProvider({ children }: { children: ReactNode }) {
  const [environment, setEnvironment] = useState<MotionEnvironment>(initialEnvironment);
  const snapshot = useMemo(() => resolveMotionPreference(environment), [environment]);

  const setMotionMode = useCallback((mode: MotionMode) => {
    setEnvironment((current) => current.mode === mode ? current : { ...current, mode });
    try {
      window.localStorage.setItem(CARESYNC_MOTION_STORAGE_KEY, mode);
    } catch {
      // Preference persistence is optional when storage is unavailable.
    }
  }, []);

  useLayoutEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const previousHtml = html.getAttribute('data-caresync-motion');
    const previousBody = body.getAttribute('data-caresync-motion');

    html.setAttribute('data-caresync-motion', snapshot.dataValue);
    body.setAttribute('data-caresync-motion', snapshot.dataValue);

    return () => {
      restoreAttribute(html, previousHtml);
      restoreAttribute(body, previousBody);
    };
  }, [snapshot.dataValue]);

  useEffect(() => {
    const reducedQuery = typeof window.matchMedia === 'function'
      ? window.matchMedia(REDUCED_MOTION_QUERY)
      : null;
    const pointerQuery = typeof window.matchMedia === 'function'
      ? window.matchMedia(FINE_POINTER_QUERY)
      : null;

    const updateEnvironment = () => {
      setEnvironment((current) => {
        const next: MotionEnvironment = {
          mode: current.mode,
          prefersReducedMotion: reducedQuery?.matches ?? false,
          documentVisible: documentIsVisible(),
          finePointer: pointerQuery?.matches ?? false,
        };
        return current.prefersReducedMotion === next.prefersReducedMotion
          && current.documentVisible === next.documentVisible
          && current.finePointer === next.finePointer
          ? current
          : next;
      });
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== CARESYNC_MOTION_STORAGE_KEY && event.key !== null) return;
      const mode = event.key === CARESYNC_MOTION_STORAGE_KEY
        ? parseMotionMode(event.newValue)
        : safeStoredMode();
      setEnvironment((current) => current.mode === mode ? current : { ...current, mode });
    };

    const unsubscribeReduced = reducedQuery
      ? subscribeToMediaQuery(reducedQuery, updateEnvironment)
      : () => undefined;
    const unsubscribePointer = pointerQuery
      ? subscribeToMediaQuery(pointerQuery, updateEnvironment)
      : () => undefined;

    document.addEventListener('visibilitychange', updateEnvironment);
    window.addEventListener('storage', handleStorage);
    updateEnvironment();

    return () => {
      unsubscribeReduced();
      unsubscribePointer();
      document.removeEventListener('visibilitychange', updateEnvironment);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const value = useMemo<MotionContextValue>(() => ({
    ...snapshot,
    setMotionMode,
  }), [setMotionMode, snapshot]);

  return <MotionContext.Provider value={value}>{children}</MotionContext.Provider>;
}

export function useMotion(): MotionContextValue {
  const value = useContext(MotionContext);
  if (!value) throw new Error('useMotion must be used within MotionProvider');
  return value;
}
