import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ThemeProvider } from 'styled-components';
import { describe, expect, it } from 'vitest';
import { workspaceTheme } from '../../styles/theme';
import { ScreeningIdentityWarning } from './JobsPage';

const renderWarning = (subjectNameMatch: boolean) => renderToStaticMarkup(
  createElement(
    ThemeProvider,
    { theme: workspaceTheme },
    createElement(ScreeningIdentityWarning, {
      subjectName: 'Amina Noor-Smith',
      accountNameSnapshot: 'Amina Noor',
      subjectNameMatch,
      mismatchResolution: subjectNameMatch
        ? 'matched'
        : 'candidate_attests_same_person',
    }),
  ),
);

describe('screening identity reconciliation warning', () => {
  it('shows the employer-authorized mismatch evidence with bounded caution copy', () => {
    const markup = renderWarning(false);

    expect(markup).toContain('Name mismatch requires employer review');
    expect(markup).toContain('Amina Noor-Smith');
    expect(markup).toContain('Amina Noor');
    expect(markup).toContain('not employer identity verification');
    expect(markup).not.toContain('reviewer_user_id');
    expect(markup).not.toContain('Internal review note');
  });

  it('does not surface a warning for a canonical matched identity', () => {
    expect(renderWarning(true)).toBe('');
  });
});
