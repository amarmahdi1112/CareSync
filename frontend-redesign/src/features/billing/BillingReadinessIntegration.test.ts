import { describe, expect, it } from "vitest";
import admissionsSource from "../admissions/AdmissionsPage.tsx?raw";
import childProfileSource from "../children/ChildProfilePage.tsx?raw";
import familyProfileSource from "../families/FamilyProfilePage.tsx?raw";
import billingPageSource from "./BillingPage.tsx?raw";
import readinessPanelSource from "./BillingReadinessPanel.tsx?raw";
import { realtimeRouteCoverage } from "../../realtime/realtimeCoverage";

describe("enrollment-to-finance integration", () => {
  it("mounts readiness only for leadership with the literal billing read grant", () => {
    for (const source of [admissionsSource, childProfileSource, familyProfileSource]) {
      expect(source).toContain("hasExplicitPermission");
      expect(source).toContain("ACCESS.billingRead");
      expect(source).toMatch(/owner.*administrator|administrator.*owner/s);
    }
    expect(admissionsSource).toContain("<BillingReadinessPanel");
    expect(familyProfileSource).toContain("<FamilyFinanceCard");
    expect(childProfileSource).toContain("<FamilyFinanceCard");
    expect(childProfileSource).toContain("<ChildFinanceCard");
  });

  it("keeps child money language attribution-only while family cards own settlement", () => {
    expect(childProfileSource).toContain("ChildFinanceCard");
    expect(childProfileSource).not.toContain("childOutstanding");
    expect(childProfileSource).not.toContain("childPaid");
    expect(familyProfileSource).toContain("FamilyFinanceCard");
    expect(billingPageSource).toContain("Enrollment readiness and the billing ledger");
  });

  it("uses server-bound internal actions and exposes readiness in billing reports", () => {
    expect(readinessPanelSource).toContain("<ItemLink to={item.action_path}>");
    expect(readinessPanelSource).not.toContain("dangerouslySetInnerHTML");
    expect(billingPageSource).toContain("fetchBillingReadiness");
    expect(billingPageSource).toContain("<BillingReadinessPanel");
    expect(billingPageSource).toContain('status="live"');
  });

  it("refreshes every mounted projection after enrollment or ledger changes", () => {
    for (const surface of ["admissions", "families", "children"] as const) {
      expect(realtimeRouteCoverage[surface].entities).toEqual(
        expect.arrayContaining([
          "family",
          "child",
          "enrollment",
          "billing_account",
          "billing_rate_plan",
          "billing_agreement",
        ]),
      );
    }
    for (const surface of ["families", "children"] as const) {
      expect(realtimeRouteCoverage[surface].entities).toEqual(
        expect.arrayContaining([
          "billing_invoice",
          "billing_payment",
          "billing_allocation",
          "billing_credit",
        ]),
      );
    }
  });

  it("does not tell operators that already-released authority is still future work", () => {
    for (const source of [childProfileSource, familyProfileSource]) {
      expect(source).not.toContain("arrives in 0029");
      expect(source).not.toContain("until 0029");
    }
  });
});
