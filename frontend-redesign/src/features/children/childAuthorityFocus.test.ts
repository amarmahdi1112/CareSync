import { describe, expect, it } from 'vitest';
import { familyAuthorityDecisionPath, parseChildAuthorityRouteFocus } from './childAuthorityFocus';

const ID = '123e4567-e89b-42d3-a456-426614174000';

describe('parseChildAuthorityRouteFocus', () => {
  it('maps each exact command-receipt query to its authority record', () => {
    expect(parseChildAuthorityRouteFocus(`?release_authorization_id=${ID}`)).toEqual({
      state: 'valid', focus: { kind: 'release_authorization', id: ID }, message: null,
    });
    expect(parseChildAuthorityRouteFocus(`?release_rule_id=${ID}`).focus?.kind).toBe('release_rule');
    expect(parseChildAuthorityRouteFocus(`?consent_id=${ID}`).focus?.kind).toBe('consent');
  });

  it('ignores unrelated child-profile destinations', () => {
    expect(parseChildAuthorityRouteFocus(`?enrollment_id=${ID}`)).toEqual({ state: 'none', focus: null, message: null });
    expect(parseChildAuthorityRouteFocus(`?toString=${ID}`)).toEqual({ state: 'none', focus: null, message: null });
    expect(parseChildAuthorityRouteFocus(`?constructor=${ID}`)).toEqual({ state: 'none', focus: null, message: null });
  });

  it('fails closed for mixed, duplicate, or malformed authority targets', () => {
    expect(parseChildAuthorityRouteFocus(`?consent_id=${ID}&release_rule_id=${ID}`).state).toBe('invalid');
    expect(parseChildAuthorityRouteFocus(`?consent_id=${ID}&consent_id=${ID}`).state).toBe('invalid');
    expect(parseChildAuthorityRouteFocus('?consent_id=not-a-uuid').state).toBe('invalid');
    expect(parseChildAuthorityRouteFocus(`?consent_id=${ID}&tab=notes`).state).toBe('invalid');
  });

  it('builds exact family-workspace links for every child authority lane', () => {
    expect(familyAuthorityDecisionPath('family/one', { kind: 'release_authorization', id: ID })).toBe(`/families/family%2Fone?release_authorization_id=${ID}`);
    expect(familyAuthorityDecisionPath('family-one', { kind: 'release_rule', id: ID })).toBe(`/families/family-one?release_rule_id=${ID}`);
    expect(familyAuthorityDecisionPath('family-one', { kind: 'consent', id: ID })).toBe(`/families/family-one?consent_id=${ID}`);
  });
});
