import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ThemeProvider } from 'styled-components';
import { describe, expect, it } from 'vitest';
import { workspaceTheme } from '../../styles/theme';
import type { CandidatePathway, ScreeningSchemaVersion } from './hiringApi';
import { ProvisioningAction } from './JobsPage';

const renderAction = (
  screeningSchemaVersion: ScreeningSchemaVersion,
  pathway: CandidatePathway,
  certificationVerificationStatus: 'unverified' | 'pending' | 'verified' | 'rejected' = 'unverified',
) => renderToStaticMarkup(
  createElement(
    ThemeProvider,
    { theme: workspaceTheme },
    createElement(ProvisioningAction, {
      pathway,
      certificationVerificationStatus,
      screeningSchemaVersion,
      busy: false,
      defaultLabel: 'Hire & provision',
      onStart: () => undefined,
    }),
  ),
);

describe('admin provisioning action rendering', () => {
  it('disables and renames the generic action for a 0030 pure driver', () => {
    const markup = renderAction('0030', 'driver');

    expect(markup).toContain('disabled=""');
    expect(markup).toContain('Driver provisioning deferred');
    expect(markup).toContain('Least-privilege driver provisioning is deferred');
    expect(markup).not.toContain('Hire &amp; provision');
  });

  it('limits a 0030 educator-driver action to educator access in visible copy', () => {
    const markup = renderAction('0030', 'educator_driver', 'verified');

    expect(markup).not.toContain('disabled=""');
    expect(markup).toContain('Provision educator only');
    expect(markup).toContain('Transport authority is not granted by this action');
    expect(markup).toContain('Employer-accepted ECE certification review is recorded');
  });

  it('defers the 0030 student pathway instead of offering generic educator access', () => {
    const markup = renderAction('0030', 'student_educator');

    expect(markup).toContain('disabled=""');
    expect(markup).toContain('Student provisioning deferred');
    expect(markup).toContain('dedicated trainee/student role is not available');
    expect(markup).not.toContain('Hire &amp; provision');
  });

  it('blocks an educator until employer ECE review is accepted', () => {
    const markup = renderAction('0030', 'educator', 'pending');

    expect(markup).toContain('disabled=""');
    expect(markup).toContain('Employer ECE review required');
    expect(markup).toContain('Candidate confirmation or OCR extraction alone is not sufficient');
  });

  it('shows recorded employer ECE review when educator provisioning is ready', () => {
    const markup = renderAction('0030', 'educator', 'verified');

    expect(markup).not.toContain('disabled=""');
    expect(markup).toContain('Hire &amp; provision');
    expect(markup).toContain('Employer-accepted ECE certification review is recorded');
  });

  it('leaves the 0028 driver action and copy unchanged', () => {
    const markup = renderAction(null, 'driver');

    expect(markup).not.toContain('disabled=""');
    expect(markup).toContain('Hire &amp; provision');
    expect(markup).not.toContain('driver provisioning is deferred');
    expect(markup).not.toContain('Transport authority');
  });
});
