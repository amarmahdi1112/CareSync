import { describe, expect, it } from 'vitest';
import { formatProgramType, normalizeProgramType } from './programTypes';

describe('licensed program types', () => {
  it('uses friendly labels for the canonical API values', () => {
    expect(formatProgramType('daycare')).toBe('Daycare');
    expect(formatProgramType('out_of_school_care')).toBe('OSC (Out-of-School Care)');
  });

  it('normalizes supported legacy aliases without exposing them as new choices', () => {
    expect(normalizeProgramType('OSC')).toBe('out_of_school_care');
    expect(normalizeProgramType('preschool')).toBe('daycare');
    expect(normalizeProgramType('unknown')).toBeNull();
  });
});
