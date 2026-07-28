import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ThemeProvider } from 'styled-components';
import { describe, expect, it } from 'vitest';
import { workspaceTheme } from '../../styles/theme';
import { DailyClosePreview } from './DailyClosePreview';
import { dailyClosePreviewFixture } from './dailyCloseTestData';

function renderPreview(): string {
  return renderToStaticMarkup(createElement(
    ThemeProvider,
    { theme: workspaceTheme },
    createElement(DailyClosePreview, { preview: dailyClosePreviewFixture }),
  ));
}

describe('DailyClosePreview rendering', () => {
  it('labels the projection as read-only facts without certification, compliance, or guardian delivery', () => {
    const markup = renderPreview();
    expect(markup).toContain('Daily close preview');
    expect(markup).toContain('Read-only facts preview');
    expect(markup).toContain('does not certify completeness or compliance');
    expect(markup).toContain('deliver anything to guardians');
  });

  it('renders bounded room totals, all six care counts, outcomes, statuses, and five attention flags', () => {
    const markup = renderPreview();
    for (const label of ['Feeding', 'Diaper', 'Toilet', 'Sleep', 'Mood', 'Activity']) expect(markup).toContain(label);
    for (const label of ['administered', 'refused', 'omitted', 'draft', 'under review', 'finalized']) expect(markup).toContain(label);
    for (const label of ['Open sleep', 'Medication refused', 'Medication omitted', 'Incident draft', 'Incident under review']) expect(markup).toContain(label);
    expect(markup).toContain('Noor Ali');
    expect(markup).toContain('2h accumulated attendance');
  });

  it('exposes accessible search and filter controls for a responsive child roster', () => {
    const markup = renderPreview();
    expect(markup).toContain('aria-label="Search daily close children"');
    expect(markup).toContain('role="group" aria-label="Filter daily close children"');
    expect(markup).toContain('role="list" aria-label="Daily close child facts"');
    expect(markup).toContain('role="listitem"');
    expect(markup).toContain('role="group" aria-label="Attention flags for Noor Ali"');
  });
});
