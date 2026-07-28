import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ACCESS, hasExplicitPermission } from "../../auth/accessModel";
import { useSession } from "../../auth/SessionContext";
import { useRealtimeRefresh } from "../../realtime/RealtimeContext";
import { billingApi } from "./billingApi";
import type { BillingCapability } from "./types";

export type BillingCapabilityPhase =
  | "checking"
  | "enabled"
  | "disabled"
  | "error";

export interface BillingCapabilityState {
  phase: BillingCapabilityPhase;
  enabled: boolean;
  live: boolean;
  capability: BillingCapability | null;
  error: string | null;
  retry: () => void;
}

type InternalCapabilityState = Omit<BillingCapabilityState, "retry">;

const disabled: InternalCapabilityState = {
  phase: "disabled",
  enabled: false,
  live: false,
  capability: null,
  error: null,
};
const BillingCapabilityContext = createContext<BillingCapabilityState | null>(
  null,
);

export function billingCapabilityIsLive(
  capability: BillingCapability | null | undefined,
): boolean {
  return (
    capability?.billing_mode === "manual" &&
    capability.manual_activated === true &&
    capability.runtime_available === true &&
    capability.writes_available === true
  );
}

export function BillingCapabilityProvider({
  children,
}: {
  children: ReactNode;
}) {
  const session = useSession();
  const organizationId = session.user?.organization_id || "";
  const allowed =
    session.status === "authenticated" &&
    (session.user?.role?.key === "owner" ||
      session.user?.role?.key === "administrator") &&
    hasExplicitPermission(session.user, ACCESS.billingRead);
  const [retryRevision, setRetryRevision] = useState(0);
  const retry = useCallback(() => {
    if (allowed && organizationId)
      setRetryRevision((current) => current + 1);
  }, [allowed, organizationId]);
  const [state, setState] = useState<InternalCapabilityState>(
    allowed
      ? {
          phase: "checking",
          enabled: false,
          live: false,
          capability: null,
          error: null,
        }
      : disabled,
  );

  useEffect(() => {
    if (!allowed || !organizationId) {
      setState(disabled);
      return;
    }
    const controller = new AbortController();
    setState({
      phase: "checking",
      enabled: false,
      live: false,
      capability: null,
      error: null,
    });
    void billingApi
      .capability(organizationId, controller.signal)
      .then((capability) => {
        if (controller.signal.aborted) return;
        setState({
          phase: "enabled",
          enabled: capability.runtime_available === true,
          live: billingCapabilityIsLive(capability),
          capability,
          error: null,
        });
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted)
          setState({
            phase: "error",
            enabled: false,
            live: false,
            capability: null,
            error:
              caught instanceof Error && caught.message.trim()
                ? caught.message
                : "CareSync could not verify the protected billing capability.",
          });
      });
    return () => controller.abort();
  }, [allowed, organizationId, retryRevision]);

  useRealtimeRefresh({
    scope: "billing-capability",
    organizationId,
    enabled: allowed,
    entityTypes: ["billing_manual_activation"],
    refresh: async () => {
      const capability = await billingApi.capability(organizationId);
      setState({
        phase: "enabled",
        enabled: capability.runtime_available === true,
        live: billingCapabilityIsLive(capability),
        capability,
        error: null,
      });
    },
  });

  const value = useMemo(() => ({ ...state, retry }), [retry, state]);
  return (
    <BillingCapabilityContext.Provider value={value}>
      {children}
    </BillingCapabilityContext.Provider>
  );
}

export function useBillingCapability(): BillingCapabilityState {
  return (
    useContext(BillingCapabilityContext) ?? {
      ...disabled,
      retry: () => undefined,
    }
  );
}
