import {
  BanknotesIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import styled from "styled-components";
import {
  GlassPanel,
  StatusChip,
} from "../../components/ui/Primitives";
import type { ResourceStatus } from "../../hooks/useCommandData";
import { formatCadMinor } from "./billingModel";
import type { FamilyFinanceSummaryResponse } from "./billingReadinessApi";

const Card = styled(GlassPanel)`
  display: grid;
  overflow: hidden;
  border-radius: ${({ theme }) => theme.radius.md};
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 19px 15px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};

  h2 {
    margin: 0;
    font-family: "CareSync Display", sans-serif;
    font-size: 1rem;
    font-weight: 540;
    letter-spacing: -0.02em;
  }
  p {
    margin: 5px 0 0;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.72rem;
    line-height: 1.5;
  }
`;

const AccountLine = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 12px 19px;
  border-bottom: 1px solid ${({ theme }) => theme.color.border};
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  font-size: 0.72rem;

  strong {
    color: ${({ theme }) => theme.color.text};
    font-weight: 600;
  }
`;

const Metrics = styled.dl`
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 0;

  > div {
    min-width: 0;
    padding: 15px 17px;
    border-right: 1px solid ${({ theme }) => theme.color.border};
    border-bottom: 1px solid ${({ theme }) => theme.color.border};
  }
  > div:nth-child(4n) {
    border-right: 0;
  }
  dt {
    overflow: hidden;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.66rem;
    letter-spacing: 0.05em;
    text-overflow: ellipsis;
    text-transform: uppercase;
    white-space: nowrap;
  }
  dd {
    margin: 7px 0 0;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.96rem;
    font-variant-numeric: tabular-nums;
    font-weight: 570;
  }
  small {
    display: block;
    margin-top: 4px;
    color: ${({ theme }) => theme.color.textMuted};
    font-size: 0.65rem;
    line-height: 1.4;
  }

  @media (max-width: 760px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    > div:nth-child(2n) {
      border-right: 0;
    }
  }
`;

const Footer = styled.footer`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 19px;
  color: ${({ theme }) => theme.color.textMuted};
  font-size: 0.68rem;
  line-height: 1.5;

  a {
    flex: 0 0 auto;
    color: ${({ theme }) => theme.color.cyan};
    font-weight: 600;
  }
  a:hover {
    text-decoration: underline;
  }

  @media (max-width: 560px) {
    align-items: flex-start;
    flex-direction: column;
  }
`;

const State = styled.div`
  display: grid;
  min-height: 142px;
  place-items: center;
  padding: 24px;
  color: ${({ theme }) => theme.color.textMuted};
  background: ${({ theme }) => theme.color.surfaceStrong};
  text-align: center;

  svg {
    width: 27px;
    margin: 0 auto 9px;
    color: ${({ theme }) => theme.color.cyan};
  }
  strong {
    display: block;
    color: ${({ theme }) => theme.color.text};
    font-size: 0.8rem;
  }
  p {
    max-width: 500px;
    margin: 5px 0 0;
    font-size: 0.72rem;
    line-height: 1.5;
  }
`;

export interface FamilyFinanceCardProps {
  status: ResourceStatus;
  data: FamilyFinanceSummaryResponse | null;
  message?: string;
}

export default function FamilyFinanceCard({
  status,
  data,
  message,
}: FamilyFinanceCardProps) {
  const loading = status === "idle" || status === "loading";
  const accountPath = data?.account
    ? `/billing?view=accounts&account=${encodeURIComponent(data.account.id)}`
    : "/billing?view=accounts";

  return (
    <Card
      as="section"
      aria-labelledby="family-finance-title"
      aria-busy={loading}
    >
      <Header>
        <div>
          <h2 id="family-finance-title">Family finance</h2>
          <p>
            Family-account invoice and off-platform payment recording summary.
          </p>
        </div>
        {data?.account ? (
          <StatusChip $tone="success">Account open</StatusChip>
        ) : data ? (
          <StatusChip $tone="warning">Account needed</StatusChip>
        ) : null}
      </Header>

      {status === "error" ? (
        <State role="alert">
          <div>
            <ExclamationTriangleIcon />
            <strong>Family finance is unavailable</strong>
            <p>{message || "Refresh after the connection returns."}</p>
          </div>
        </State>
      ) : loading ? (
        <State>
          <div>
            <p>Connecting the family account and ledger…</p>
          </div>
        </State>
      ) : !data ? (
        <State>
          <div>
            <BanknotesIcon />
            <strong>No family finance summary</strong>
            <p>This record has not returned a current billing projection.</p>
          </div>
        </State>
      ) : (
        <>
          <AccountLine>
            <strong>{data.family.name}</strong>
            <span>·</span>
            {data.account ? (
              <>
                <span>{data.account.account_number}</span>
                <span>·</span>
                <span>Payer: {data.account.payer_name}</span>
              </>
            ) : (
              <span>No family billing account is open.</span>
            )}
          </AccountLine>
          <Metrics aria-label="Family account settlement totals">
            <div>
              <dt>Invoiced</dt>
              <dd>{formatCadMinor(data.invoice_summary.total_minor)}</dd>
              <small>{data.invoice_summary.invoice_count} family invoices</small>
            </div>
            <div>
              <dt>Outstanding</dt>
              <dd>{formatCadMinor(data.invoice_summary.outstanding_minor)}</dd>
              <small>
                {data.invoice_summary.open_invoice_count} open family invoices
              </small>
            </div>
            <div>
              <dt>Payments recorded</dt>
              <dd>{formatCadMinor(data.payment_summary.recorded_minor)}</dd>
              <small>
                {data.payment_summary.payment_count} off-platform records
              </small>
            </div>
            <div>
              <dt>Unapplied</dt>
              <dd>{formatCadMinor(data.payment_summary.unapplied_minor)}</dd>
              <small>Held on this family account</small>
            </div>
          </Metrics>
          <Footer>
            <span>
              Settlement belongs to the family account. Child cards report
              charge attribution only.
            </span>
            <Link to={accountPath}>
              {data.account ? "Open family ledger" : "Create family account"}
            </Link>
          </Footer>
        </>
      )}
    </Card>
  );
}
