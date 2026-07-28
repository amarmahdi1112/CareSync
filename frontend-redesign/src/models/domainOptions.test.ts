import { describe, expect, it } from 'vitest';
import {
  CANADIAN_PROVINCE_OPTIONS,
  CANADIAN_TIMEZONE_OPTIONS,
  ROOM_AGE_GROUP_OPTIONS,
  includesDomainValue,
  normalizeCanadianProvince,
  normalizeRoomAgeGroup,
} from './domainOptions';

describe('shared Basic domain choices', () => {
  it('normalizes Canadian province abbreviations without losing unknown legacy values', () => {
    expect(normalizeCanadianProvince(' AB ')).toBe('Alberta');
    expect(normalizeCanadianProvince('pei')).toBe('Prince Edward Island');
    expect(normalizeCanadianProvince('Custom region')).toBe('Custom region');
  });

  it('normalizes common room age-group aliases', () => {
    expect(normalizeRoomAgeGroup('school age')).toBe('School-Age');
    expect(normalizeRoomAgeGroup('OSC')).toBe('School-Age');
    expect(normalizeRoomAgeGroup('mixed')).toBe('Mixed-Age');
    expect(normalizeRoomAgeGroup(null)).toBe('');
  });

  it('publishes unique values for every constrained choice set', () => {
    [CANADIAN_PROVINCE_OPTIONS, CANADIAN_TIMEZONE_OPTIONS, ROOM_AGE_GROUP_OPTIONS].forEach((options) => {
      expect(new Set(options.map((option) => option.value)).size).toBe(options.length);
    });
    expect(includesDomainValue(CANADIAN_TIMEZONE_OPTIONS, 'America/Edmonton')).toBe(true);
  });
});
