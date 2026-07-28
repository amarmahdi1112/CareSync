import {
  BanknotesIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import styled from "styled-components";
import { GlassPanel, StatusChip } from "../../components/ui/Primitives";
import type { ResourceStatus } from "../../hooks/useCommandData";
import { formatCadMinor } from "./billingModel";
import {
  billingReadinessLabel,
} from "./BillingReadinessPanel";
import type {
  BillingReadinessStatus,
  ChildFinanceSummary,
} from "./billingReadinessApi";

const Card = styled(GlassPanel)`
  display: grid;
  overflow: hidden;
  border-radius: ${({ theme }) => theme.radius.md};
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 17px 18px 14px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 0.98rem;
    font-weight: 540;
    letter-spacing: -0.02em;
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.7rem;
    line-height: 1.5;
  }
`;

const Metrics = styled.dl`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;

  > div {
    min-width: 0;
    padding: 14px 17px;
    border-right: 1px solid ${({ theme }) => theme.color.border};
    border-bottom: 1px solid ${({ theme }) => theme.color.border};
    background: ${({ theme }) => theme.color.surfaceStrong};
  }
  > div:nth-child(2n) {
    border-right: 0;
  }
  dt {
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.64rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  dd {
    margin: 6px 0 0;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.9rem;
    font-variant-numeric: tabular-nums;
    font-weight: 570;
  }
  small {
    display: block;
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.63rem;
    line-height: 1.4;
  }
`;

const Boundary = styled.p`
  margin: 0;
  padding: 11px 18px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.67rem;
  line-height: 1.5;
`;

const State = styled.div`
  display: grid;
  min-height: 132px;
  place-items: center;
  padding: 22px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  text-align: center;

  svg {
    width: 26px;
    margin: 0 auto 8px;
    color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.78rem;
  }
  p {
    max-width: 450px;
    margin: 5px 0 0;
    font-size: 0.7rem;
    line-height: 1.5;
  }
`;

function readinessTone(
  status: BillingReadinessStatus | null,
): "success" | "warning" | "info" | "neutral" {
  if (status === null) return "neutral";
  if (status === "setup_ready") return "success";
  if (status === "needs_review" || status === "agreement_scope_conflict")
    return "warning";
  return "info";
}

export interface ChildFinanceCardProps {
  status: ResourceStatus;
  data: ChildFinanceSummary | null;
  message?: string;
}

export default function ChildFinanceCard({
  status,
  data,
  message,
}: ChildFinanceCardProps) {
  const loading = status === "idle" || status === "loading";
  const charges = data?.charge_attribution;

  return (
    <Card
      as="section"
      aria-labelledby="child-finance-title"
      aria-busy={loading}
    >
      <Header>
        <div>
          <h2 id="child-finance-title">Charge attribution</h2>
          <p>
            Care charges attributed to this child on the family’s invoices.
          </p>
        </div>
        {data && (
          <StatusChip $tone={readinessTone(data.readiness_status)}>
            {data.readiness_status
              ? billingReadinessLabel(data.readiness_status)
              : "Historical record"}
          </StatusChip>
        )}
      </Header>

      {status === "error" ? (
        <State role="alert">
          <div>
            <ExclamationTriangleIcon />
            <strong>Child charge attribution is unavailable</strong>
            <p>{message || "Refresh after the connection returns."}</p>
          </div>
        </State>
      ) : loading ? (
        <State>
          <div>
            <p>Connecting this child to family invoice lines…</p>
          </div>
        </State>
      ) : !data || !charges ? (
        <State>
          <div>
            <BanknotesIcon />
            <strong>No child charge attribution</strong>
            <p>This child has not returned a current finance projection.</p>
          </div>
        </State>
      ) : (
        <>
          <Metrics aria-label={`${data.child_name} charge attribution`}>
            <div>
              <dt>Gross care charges</dt>
              <dd>{formatCadMinor(charges.gross_minor)}</dd>
              <small>{charges.line_count} attributed invoice lines</small>
            </div>
            <div>
              <dt>Funding offset</dt>
              <dd>{formatCadMinor(charges.funding_minor)}</dd>
              <small>Reduces the family charge projection</small>
            </div>
            <div>
              <dt>Family charge</dt>
              <dd>{formatCadMinor(charges.subtotal_minor)}</dd>
              <small>Before projected tax</small>
            </div>
            <div>
              <dt>Attributed total</dt>
              <dd>{formatCadMinor(charges.total_minor)}</dd>
              <small>
                Across {charges.invoice_count} family invoices ·{" "}
                {formatCadMinor(charges.tax_minor)} tax
              </small>
            </div>
          </Metrics>
          <Boundary>
            Payments, credits, and balances settle at the family-account level
            and are intentionally not assigned to a child.
          </Boundary>
        </>
      )}
    </Card>
  );
}
