import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from 'styled-components';
import { describe, expect, it } from 'vitest';
import { workspaceTheme } from '../../styles/theme';
import RecordReadinessPanel, { readinessActionLabel } from './RecordReadinessPanel';

const data = {
  items: [{
    key: 'open-unassigned:enrollment-1', code: 'open_unassigned_enrollment' as const, severity: 'warning' as const,
    family_id: 'family-1', child_id: 'child-1', enrollment_id: 'enrollment-1', facility_id: 'facility-1',
    title: 'Placement needed', message: 'Approve a compatible room before care begins.',
    action_route: '/rooms?facility_id=facility-1&placement_enrollment_id=enrollment-1',
  }],
  total: 1, limit: 8, offset: 0, counts: { critical: 0, warning: 1, info: 0 },
};

function render(status: 'live' | 'empty' | 'error', message?: string): string {
  return renderToStaticMarkup(createElement(
    ThemeProvider,
    { theme: workspaceTheme },
    createElement(MemoryRouter, null, createElement(RecordReadinessPanel, {
      status,
      data: status === 'empty' ? { ...data, items: [], total: 0, counts: { critical: 0, warning: 0, info: 0 } } : status === 'error' ? null : data,
      message,
    })),
  ));
}

describe('RecordReadinessPanel rendering', () => {
  it('renders the server-authored remediation route and bounded severity counts', () => {
    const markup = render('live');
    expect(markup).toContain('Record readiness');
    expect(markup).toContain('1 warning');
    expect(markup).toContain('/rooms?facility_id=facility-1&amp;placement_enrollment_id=enrollment-1');
    expect(markup).toContain('Placement needed');
    expect(markup).toContain('Select and approve a room');
    expect(markup).toContain('<ul');
    expect(markup).toMatch(/<li[^>]*><a[^>]*href="\/rooms\?facility_id=facility-1&amp;placement_enrollment_id=enrollment-1"/);
    expect(markup).not.toContain('role="listitem"');
  });

  it('names the pending-family destination instead of showing an unexplained arrow', () => {
    expect(readinessActionLabel({
      ...data.items[0],
      title: 'Adel Kumere Asefa: family activation required',
      action_route: '/families/family-1?focus=family-status&child_id=child-1&enrollment_id=enrollment-1',
    })).toBe('Open family status review');
  });

  it('keeps transport failure separate from a clean readiness queue', () => {
    expect(render('error', 'Connection unavailable')).toContain('Readiness queue unavailable');
    expect(render('empty')).toContain('No current review signals');
  });
});
