import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ServerStyleSheet, StyleSheetManager, ThemeProvider } from 'styled-components';
import { describe, expect, it, vi } from 'vitest';
import { workspaceTheme } from '../styles/theme';
import type { ChildcareCommandJournalEntry } from '../api/childcareCommandJournal';
import {
  ChildcareCommandRecoveryContext,
  type ChildcareCommandRecoveryValue,
} from './ChildcareCommandRecoveryContext';
import { ChildcareCommandRecoverySurface } from './ChildcareCommandRecoverySurface';

const ACTOR_ID = '10000000-0000-4000-8000-000000000001';
const ORGANIZATION_ID = '20000000-0000-4000-8000-000000000001';
const OPERATION_ID = '30000000-0000-4000-8000-000000000001';
const TARGET_ID = '40000000-0000-4000-8000-000000000001';

function entry(status: ChildcareCommandJournalEntry['status']): ChildcareCommandJournalEntry {
  return {
    schemaVersion: 2,
    key: `v1:${ACTOR_ID}:${ORGANIZATION_ID}:${OPERATION_ID}`,
    actorUserId: ACTOR_ID,
    organizationId: ORGANIZATION_ID,
    clientOperationId: OPERATION_ID,
    commandType: 'family.update',
    targetType: 'family',
    expectedTargetId: TARGET_ID,
    expectedActionOwnerId: null,
    createdAt: '2026-07-17T10:00:00Z',
    status,
  };
}

function value(overrides: Partial<ChildcareCommandRecoveryValue>): ChildcareCommandRecoveryValue {
  return {
    activeEntry: null,
    blockReason: null,
    checking: false,
    ready: true,
    laneBlocked: false,
    lastResolved: null,
    lastFinalAbsenceAcknowledgedOperationId: null,
    execute: vi.fn(),
    checkSavedResult: vi.fn(),
    acknowledgeFinalAbsence: vi.fn(),
    dismissResolved: vi.fn(),
    ...overrides,
  };
}

function renderSurface(context: ChildcareCommandRecoveryValue): { html: string; css: string } {
  const sheet = new ServerStyleSheet();
  try {
    const html = renderToStaticMarkup(createElement(
      MemoryRouter,
      null,
      createElement(
        ThemeProvider,
        { theme: workspaceTheme },
        createElement(
          StyleSheetManager,
          { sheet: sheet.instance },
          createElement(
            ChildcareCommandRecoveryContext.Provider,
            { value: context },
            createElement(ChildcareCommandRecoverySurface),
          ),
        ),
      ),
    ));
    return { html, css: sheet.getStyleTags() };
  } finally {
    sheet.seal();
  }
}

describe('childcare recovery surface', () => {
  it('uses explicit final-absence acknowledgement without exposing durable identifiers', () => {
    const { html } = renderSurface(value({ activeEntry: entry('absent_final'), laneBlocked: true }));
    expect(html).toContain('I reviewed it — allow a new change');
    expect(html).toContain('will never resend it automatically');
    expect(html).not.toContain(OPERATION_ID);
    expect(html).not.toContain(ACTOR_ID);
    expect(html).not.toContain(ORGANIZATION_ID);
  });

  it('renders a target-bound resolved route and responsive reduced-motion styles', () => {
    const { html, css } = renderSurface(value({
      lastResolved: {
        clientOperationId: OPERATION_ID,
        actionRoute: `/families/${TARGET_ID}`,
        targetType: 'family',
        targetId: TARGET_ID,
        version: 8,
      },
    }));
    expect(html).toContain(`href="/families/${TARGET_ID}"`);
    expect(html).toContain('version 8');
    expect(css).toMatch(/max-width:\s*620px/);
    expect(css).toMatch(/prefers-reduced-motion:\s*reduce/);
    expect(css).toMatch(/grid-template-columns:auto minmax\(0,\s*1fr\)/);
  });

  it('renders a delayed nested-admission recovery as the refreshed owning application', () => {
    const applicationId = '50000000-0000-4000-8000-000000000001';
    const supersededOfferId = '60000000-0000-4000-8000-000000000001';
    const { html } = renderSurface(value({
      lastResolved: {
        clientOperationId: OPERATION_ID,
        actionRoute: `/admissions/applications/${applicationId}`,
        targetType: 'admission_application',
        targetId: applicationId,
        version: 12,
      },
    }));
    expect(html).toContain('refreshed the canonical admission application at version 12');
    expect(html).toContain(`href="/admissions/applications/${applicationId}"`);
    expect(html).not.toContain(supersededOfferId);
  });
});
