import {
  CheckCircleIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
  ShieldExclamationIcon,
} from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import styled from "styled-components";
import { GlassPanel, StatusChip } from "../../components/ui/Primitives";
import type { ResourceStatus } from "../../hooks/useCommandData";
import type {
  BillingReadinessItem,
  BillingReadinessResponse,
  BillingReadinessStatus,
} from "./billingReadinessApi";

const Panel = styled(GlassPanel)`
  display: grid;
  gap: 0;
  overflow: hidden;
  border-radius: ${({ theme }) => theme.radius.md};
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 19px 20px 16px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1.05rem;
    font-weight: 540;
    letter-spacing: -0.025em;
  }
  p {
    max-width: 660px;
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.75rem;
    line-height: 1.55;
  }

  @media (max-width: 620px) {
    flex-direction: column;
  }
`;

const Counts = styled.div`
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;

  @media (max-width: 620px) {
    justify-content: flex-start;
  }
`;

const List = styled.ul`
  display: grid;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const ListItem = styled.li`
  min-width: 0;
  & + & {
    border-top: 1px solid ${({ theme }) => theme.color.border};
  }
`;

const ItemLink = styled(Link)`
  display: grid;
  min-width: 0;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 82px;
  padding: 13px 20px;
  color: inherit;
  background: ${({ theme }) => theme.color.surfaceStrong};
  transition:
    background ${({ theme }) => theme.motion.fast} ease,
    transform ${({ theme }) => theme.motion.fast} ${({ theme }) => theme.motion.ease};

  &:hover {
    background: ${({ theme }) => theme.color.surfaceHover};
    transform: translateX(2px);
  }
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.color.cyan};
    outline-offset: -3px;
  }
  > svg:first-child {
    width: 21px;
    color: ${({ theme }) => theme.color.amber};
  }
  > svg:last-child {
    width: 17px;
    color: ${({ theme }) => theme.color.textMuted};
  }
`;

const ItemBody = styled.div`
  min-width: 0;
`;

const ItemTitle = styled.div`
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;

  strong {
    overflow: hidden;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.8rem;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;

const Detail = styled.span`
  display: block;
  margin-top: 5px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.74rem;
  line-height: 1.5;
`;

const ActionHint = styled.span`
  display: block;
  margin-top: 7px;
  color: ${({ theme }) => theme.color.cyan};
  font-size: 0.69rem;
  font-weight: 600;
`;

const State = styled.div`
  display: grid;
  min-height: 132px;
  place-items: center;
  padding: 24px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  text-align: center;

  div {
    max-width: 560px;
  }
  svg {
    width: 28px;
    margin: 0 auto 9px;
    color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.82rem;
  }
  p {
    margin: 5px 0 0;
    font-size: 0.75rem;
    line-height: 1.55;
  }
`;

const Footer = styled.p`
  margin: 0;
  padding: 11px 20px;
  border-top: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surface};
  font-size: 0.68rem;
  line-height: 1.5;
`;

const STATUS_CONTENT: Record<
  BillingReadinessStatus,
  { label: string; detail: string }
> = {
  setup_ready: {
    label: "Setup ready",
    detail:
      "The current enrollment, family account, payer, rate, and agreement align.",
  },
  needs_account: {
    label: "Family account needed",
    detail: "Open one family billing account before preparing an agreement.",
  },
  needs_payer: {
    label: "Payer needed",
    detail: "Confirm the guardian responsible for this family account.",
  },
  needs_current_enrollment: {
    label: "Current enrollment needed",
    detail: "Resolve the child’s current enrollment before configuring billing.",
  },
  needs_rate_plan: {
    label: "Compatible rate needed",
    detail: "Publish a current rate for the enrollment’s program.",
  },
  needs_agreement: {
    label: "Agreement needed",
    detail: "Create and review an agreement for this enrollment and rate.",
  },
  agreement_scope_conflict: {
    label: "Agreement scope conflict",
    detail:
      "The existing child agreement belongs to another enrollment and must be reviewed.",
  },
  needs_review: {
    label: "Billing setup needs review",
    detail: "The current canonical records do not form one safe billing setup.",
  },
};

export function billingReadinessLabel(status: BillingReadinessStatus): string {
  return STATUS_CONTENT[status].label;
}

export function billingReadinessActionLabel(
  item: BillingReadinessItem,
): string {
  switch (item.status) {
    case "setup_ready":
      return "Open this family’s invoices";
    case "needs_account":
      return "Open family account setup";
    case "needs_payer":
      return "Confirm the family payer";
    case "needs_current_enrollment":
      return "Open the child’s enrollment";
    case "needs_rate_plan":
      return "Open rate plans";
    case "needs_agreement":
      return "Create the enrollment agreement";
    case "agreement_scope_conflict":
      return "Resolve the agreement scope";
    case "needs_review":
      if (item.reason_codes.includes("billing_family_not_active")) {
        return "Review the family status";
      }
      return "Review the billing setup";
  }
}

function statusTone(
  status: BillingReadinessStatus,
): "success" | "warning" | "info" | "neutral" {
  if (status === "setup_ready") return "success";
  if (status === "needs_review" || status === "agreement_scope_conflict")
    return "warning";
  return "info";
}

export interface BillingReadinessPanelProps {
  status: ResourceStatus;
  data: BillingReadinessResponse | null;
  message?: string;
  maximumItems?: number;
}

export default function BillingReadinessPanel({
  status,
  data,
  message,
  maximumItems = 8,
}: BillingReadinessPanelProps) {
  const loading = status === "idle" || status === "loading";
  const ready = data?.counts.setup_ready ?? 0;
  const needsAction = data ? data.counts.total - ready : 0;
  const displayedItems = data?.items.slice(0, Math.max(0, maximumItems)) ?? [];

  return (
    <Panel
      as="section"
      aria-labelledby="billing-readiness-title"
      aria-busy={loading}
    >
      <Header>
        <div>
          <h2 id="billing-readiness-title">Enrollment to billing readiness</h2>
          <p>
            Connects active children and enrollments to one family account,
            payer, current rate, and reviewed agreement.
          </p>
        </div>
        {data && (
          <Counts aria-label={`${data.counts.total} billing setup records`}>
            <StatusChip $tone={ready ? "success" : "neutral"}>
              {ready} ready
            </StatusChip>
            <StatusChip $tone={needsAction ? "warning" : "neutral"}>
              {needsAction} need action
            </StatusChip>
          </Counts>
        )}
      </Header>

      {status === "error" ? (
        <State role="alert">
          <div>
            <ShieldExclamationIcon />
            <strong>Billing readiness is unavailable</strong>
            <p>{message || "Refresh after the connection returns."}</p>
          </div>
        </State>
      ) : loading ? (
        <State>
          <div>
            <p>Connecting enrollment and billing records…</p>
          </div>
        </State>
      ) : !data || data.counts.total === 0 ? (
        <State>
          <div>
            <CheckCircleIcon />
            <strong>No active enrollment billing rows</strong>
            <p>
              Add or activate children and enrollments before configuring their
              family billing setup.
            </p>
          </div>
        </State>
      ) : (
        <List aria-label="Enrollment billing setup">
          {displayedItems.map((item) => (
            <ListItem
              key={`${item.family_id}:${item.child_id}:${item.enrollment_id ?? "none"}`}
            >
              <ItemLink to={item.action_path}>
                {item.status === "setup_ready" ? (
                  <CheckCircleIcon aria-hidden="true" />
                ) : (
                  <ExclamationTriangleIcon aria-hidden="true" />
                )}
                <ItemBody>
                  <ItemTitle>
                    <strong>
                      {item.child_name} · {item.family_name}
                    </strong>
                    <StatusChip $tone={statusTone(item.status)}>
                      {billingReadinessLabel(item.status)}
                    </StatusChip>
                  </ItemTitle>
                  <Detail>{STATUS_CONTENT[item.status].detail}</Detail>
                  <ActionHint>
                    {billingReadinessActionLabel(item)}
                  </ActionHint>
                </ItemBody>
                <ChevronRightIcon aria-hidden="true" />
              </ItemLink>
            </ListItem>
          ))}
        </List>
      )}

      {data && data.items.length > displayedItems.length && (
        <Footer>
          Showing {displayedItems.length} of {data.items.length} current setup
          records.
        </Footer>
      )}
      <Footer>
        Readiness confirms record alignment only. It does not certify invoice
        accuracy, payment, funding, tax, or regulatory compliance.
      </Footer>
    </Panel>
  );
}
