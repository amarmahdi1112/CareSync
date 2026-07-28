import { describe, expect, it } from 'vitest';
import { parseMotionMode, resolveMotionPreference, type MotionEnvironment } from './motionModel';

const environment = (overrides: Partial<MotionEnvironment> = {}): MotionEnvironment => ({
  mode: 'system',
  prefersReducedMotion: false,
  documentVisible: true,
  finePointer: true,
  ...overrides,
});

describe('parseMotionMode', () => {
  it.each(['system', 'full', 'off'] as const)('accepts the persisted %s mode', (mode) => {
    expect(parseMotionMode(mode)).toBe(mode);
  });

  it.each([null, undefined, '', 'reduce', 'invalid'])('falls back to system for %s', (value) => {
    expect(parseMotionMode(value)).toBe('system');
  });
});

describe('resolveMotionPreference', () => {
  it('uses full motion when system motion is not reduced', () => {
    expect(resolveMotionPreference(environment())).toMatchObject({
      resolvedMode: 'full',
      dataValue: 'full',
      motionAllowed: true,
      autonomousAllowed: true,
      finePointer: true,
    });
  });

  it('honours the system reduced-motion preference', () => {
    expect(resolveMotionPreference(environment({ prefersReducedMotion: true }))).toMatchObject({
      resolvedMode: 'reduced',
      dataValue: 'reduced',
      motionAllowed: false,
      autonomousAllowed: false,
    });
  });

  it('allows an explicit full-motion override', () => {
    expect(resolveMotionPreference(environment({ mode: 'full', prefersReducedMotion: true }))).toMatchObject({
      resolvedMode: 'full',
      dataValue: 'full',
      motionAllowed: true,
      autonomousAllowed: true,
    });
  });

  it('disables all optional motion when explicitly off', () => {
    expect(resolveMotionPreference(environment({ mode: 'off' }))).toMatchObject({
      resolvedMode: 'off',
      dataValue: 'off',
      motionAllowed: false,
      autonomousAllowed: false,
    });
  });

  it('pauses autonomous effects while the document is hidden', () => {
    expect(resolveMotionPreference(environment({ documentVisible: false }))).toMatchObject({
      resolvedMode: 'full',
      dataValue: 'paused',
      motionAllowed: true,
      autonomousAllowed: false,
    });
  });

  it('keeps reduced and off states stable while hidden', () => {
    expect(resolveMotionPreference(environment({ prefersReducedMotion: true, documentVisible: false })).dataValue).toBe('reduced');
    expect(resolveMotionPreference(environment({ mode: 'off', documentVisible: false })).dataValue).toBe('off');
  });
});
