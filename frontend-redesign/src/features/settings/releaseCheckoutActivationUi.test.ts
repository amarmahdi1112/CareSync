import { describe, expect, it } from 'vitest';
import settingsPageSource from './SettingsPage.tsx?raw';
import settingsApiSource from './settingsApi.ts?raw';

describe('verified release activation UI boundary', () => {
  it('renders explicit prerequisites and all four irreversible review acknowledgements', () => {
    expect(settingsPageSource).toContain('Verified release checkout.');
    expect(settingsPageSource).toContain('authority_records_reviewed: true');
    expect(settingsPageSource).toContain('verification_workflow_reviewed: true');
    expect(settingsPageSource).toContain('legacy_checkout_closure_understood: true');
    expect(settingsPageSource).toContain('irreversible_activation_understood: true');
    expect(settingsPageSource).toContain('ACTIVATE VERIFIED RELEASE CHECKOUT');
    expect(settingsPageSource).toContain('There is intentionally no deactivate or override control.');
  });

  it('preserves one operation identity across an ambiguous retry and removes it after a receipt', () => {
    const activation = settingsPageSource.slice(
      settingsPageSource.indexOf('const activateVerifiedRelease'),
      settingsPageSource.indexOf('const saveProfile'),
    );
    expect(activation).toContain('localStorage.getItem(operationKey)');
    expect(activation).toContain('localStorage.setItem(operationKey, operationId)');
    expect(activation).toContain('settingsApi.activateReleaseCheckout');
    expect(activation).toContain('localStorage.removeItem(operationKey)');
    expect(activation).toContain('error.status > 0 && error.status < 500');
  });

  it('uses the exact tenant/facility endpoint and rejects cross-echoed responses', () => {
    expect(settingsApiSource).toContain('/release-checkout-activation');
    expect(settingsApiSource).toContain("assertOrganizationId(value.status.organization_id, organizationId, 'Release checkout activation')");
    expect(settingsApiSource).toContain('value.receipt.client_operation_id !== payload.client_operation_id');
    expect(settingsApiSource).toContain("receipt.action_route !== '/settings?section=facility'");
  });
});
