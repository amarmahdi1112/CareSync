export type ChildAuthorityFocusKind = 'release_authorization' | 'release_rule' | 'consent';

export interface ChildAuthorityFocus {
  kind: ChildAuthorityFocusKind;
  id: string;
}

export type ChildAuthorityRouteFocus =
  | { state: 'none'; focus: null; message: null }
  | { state: 'valid'; focus: ChildAuthorityFocus; message: null }
  | { state: 'invalid'; focus: null; message: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const AUTHORITY_KEYS = {
  release_authorization_id: 'release_authorization',
  release_rule_id: 'release_rule',
  consent_id: 'consent',
} as const;
const AUTHORITY_PARAMETERS: Record<ChildAuthorityFocusKind, keyof typeof AUTHORITY_KEYS> = {
  release_authorization: 'release_authorization_id',
  release_rule: 'release_rule_id',
  consent: 'consent_id',
};

export function familyAuthorityDecisionPath(familyId: string, focus: ChildAuthorityFocus): string {
  const parameter = AUTHORITY_PARAMETERS[focus.kind];
  return `/families/${encodeURIComponent(familyId)}?${parameter}=${encodeURIComponent(focus.id)}`;
}

export function parseChildAuthorityRouteFocus(search: string): ChildAuthorityRouteFocus {
  const parameters = new URLSearchParams(search);
  const entries = [...parameters.entries()];
  const authorityEntries = entries.filter(([key]) => Object.prototype.hasOwnProperty.call(AUTHORITY_KEYS, key));
  if (!authorityEntries.length) return { state: 'none', focus: null, message: null };
  if (authorityEntries.length !== 1 || entries.length !== 1) {
    return {
      state: 'invalid',
      focus: null,
      message: 'This authority receipt link is ambiguous or contains unsupported parameters. Open the receipt again; CareSync will not guess a record.',
    };
  }
  const [key, rawId] = authorityEntries[0];
  if (!UUID.test(rawId)) {
    return {
      state: 'invalid',
      focus: null,
      message: 'This authority receipt link contains an invalid record identifier. CareSync did not open a different record.',
    };
  }
  return {
    state: 'valid',
    focus: {
      kind: AUTHORITY_KEYS[key as keyof typeof AUTHORITY_KEYS],
      id: rawId.toLowerCase(),
    },
    message: null,
  };
}
