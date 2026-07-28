import { describe, expect, it } from 'vitest';
import rotaSource from './StaffRotaPage.tsx?raw';
import workforceSource from './WorkforcePlanningPanel.tsx?raw';
import rotationSource from './rotations/RotationPlanningPanel.tsx?raw';
import exchangeSource from './exchange/ShiftExchangePanel.tsx?raw';
import medicationSource from '../medications/MedicationPage.tsx?raw';

describe('exact notification action wiring', () => {
  it('re-reads and clears workforce locators before handing an exact target to its owner', () => {
    expect(rotaSource).toContain('resolveStaffRotaActionTarget(parsed.request');
    expect(rotaSource).toContain("clearNotificationTargets(current, ['focus', 'record'])");
    expect(rotaSource).toContain('notificationTarget={focusedWorkforceTarget}');
    expect(workforceSource).toContain('data-workforce-target');
    expect(workforceSource).toContain('focusedPatternId=');
    expect(rotationSource).toContain('data-rotation-id');
  });

  it('opens an engagement through its canonical parent and focuses only exact exchange rows', () => {
    expect(exchangeSource).toContain('posts.find(');
    expect(exchangeSource).toContain('post.id === exchangeTarget.parentEntityId');
    expect(exchangeSource).toContain('void loadReview(parent)');
    expect(exchangeSource).toContain('data-exchange-target');
    expect(exchangeSource).toContain('No different record was selected.');
  });

  it('re-reads medication plans independently of room-day filters', () => {
    expect(medicationSource).toContain('fetchMedicationPlan(requestedPlanId, organizationId');
    expect(medicationSource).toContain('data-medication-plan-id={focusedPlan.id}');
    expect(medicationSource).toContain('Room and date filters were not inferred from the notification.');
  });
});
