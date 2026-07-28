import { describe, expect, it } from 'vitest';
import {
  APP_RECOVERY_COPY,
  DEFERRED_MODULE_COPY,
  RELEASE_AUTHORIZATION_SAVED_COPY,
  RELEASE_AUTHORITY_BOUNDARY_COPY,
  SCHEDULER_PREVIEW_COPY,
} from './activeRuntimeCopy';

describe('active admin runtime user-facing copy', () => {
  it('does not direct deferred or recovery surfaces to the retired 5173 runtime', () => {
    const messages = [
      APP_RECOVERY_COPY,
      DEFERRED_MODULE_COPY,
      SCHEDULER_PREVIEW_COPY,
    ];

    for (const message of messages) {
      expect(message).not.toContain('port 5173');
    }

    expect(APP_RECOVERY_COPY).toContain('Reload the active CareSync admin interface');
    expect(DEFERRED_MODULE_COPY).toContain('this module is not enabled here yet');
    expect(SCHEDULER_PREVIEW_COPY).toContain('Real V3 scheduling is not enabled on this preview page');
  });

  it('describes the current verified-release activation boundary', () => {
    expect(RELEASE_AUTHORIZATION_SAVED_COPY).toContain(
      'Settings facility activation determines whether normal verified release is active; the staff app performs verified-recipient release.',
    );
    expect(RELEASE_AUTHORITY_BOUNDARY_COPY).toContain(
      'Settings facility activation determines whether normal verified release is active; the staff app performs verified-recipient release using these current records.',
    );
    expect(RELEASE_AUTHORIZATION_SAVED_COPY).not.toContain('later release-context gate');
    expect(RELEASE_AUTHORITY_BOUNDARY_COPY).not.toContain('later minimum-necessary release-context gate');
  });
});
