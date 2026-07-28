import { describe, expect, it } from 'vitest';

import {
  activeDeniedSuggestions,
  autoMapChildren,
  clearDeniedSources,
  exactSourceMappings,
  nameTokenKey,
  normalizeName,
  rememberDeniedSuggestion,
  rememberMappings,
  restoreRememberedMappings,
  sanitizeActiveMappings,
} from '../src/shared/matching';

describe('name normalization and exact matching', () => {
  it('normalizes accents, case, punctuation, and repeated whitespace', () => {
    expect(normalizeName("  Zoë   O’CONNOR-Smith ")).toBe('zoe o connor smith');
  });

  it('uses the same exact token key when first and last names are reversed', () => {
    expect(nameTokenKey('Jitu Regassa')).toBe(nameTokenKey('Regassa, Jitu'));
  });

  it('maps only normalized or token-exact names', () => {
    const result = autoMapChildren(
      [
        { id: 'portal-1', name: 'Jitu Regassa' },
        { id: 'portal-2', name: 'Smith, Zoë' },
      ],
      [
        { id: 'source-1', name: 'JITU REGASSA' },
        { id: 'source-2', name: 'Zoë Smith' },
      ],
    );

    expect(result).toEqual({
      mappings: { 'portal-1': 'source-1', 'portal-2': 'source-2' },
      ambiguousPortalChildIds: [],
      unmatchedPortalChildIds: [],
    });
  });

  it('does not make a fuzzy guess for a similar spelling', () => {
    const result = autoMapChildren(
      [{ id: 'portal-1', name: 'Jitu Regasa' }],
      [{ id: 'source-1', name: 'Jitu Regassa' }],
    );

    expect(result.mappings).toEqual({});
    expect(result.unmatchedPortalChildIds).toEqual(['portal-1']);
  });

  it('marks duplicate exact source names ambiguous instead of choosing one', () => {
    const result = autoMapChildren(
      [{ id: 'portal-1', name: 'Sam Lee' }],
      [
        { id: 'source-1', name: 'Sam Lee' },
        { id: 'source-2', name: 'Sam Lee' },
      ],
    );

    expect(result.mappings).toEqual({});
    expect(result.ambiguousPortalChildIds).toEqual(['portal-1']);
  });

  it('builds source-oriented UI mappings for reversed exact token order', () => {
    expect(
      exactSourceMappings(
        [{ id: 'source-1', name: 'Jitu Regassa' }],
        [{ id: 'portal-1', name: 'Regassa, Jitu' }],
      ),
    ).toEqual({ 'source-1': 'portal-1' });
  });

  it('does not auto-map a source when the portal has duplicate exact candidates', () => {
    expect(
      exactSourceMappings(
        [{ id: 'source-1', name: 'Sam Lee' }],
        [
          { id: 'portal-1', name: 'Sam Lee' },
          { id: 'portal-2', name: 'Lee, Sam' },
        ],
      ),
    ).toEqual({});
  });
});

describe('durable monthly mapping memory', () => {
  const source = [{ id: 'source-1', name: 'Shama Il Lamadeen' }];
  const portal = [{ id: 'portal-1', name: "Shama'Il Lamadeen" }];

  it('restores a validated mapping for another monthly ZIP', () => {
    const memory = rememberMappings({}, { 'source-1': 'portal-1' }, source, portal, 'room-1', '2026-07-13T00:00:00Z');

    expect(restoreRememberedMappings(memory, source, portal, 'room-1')).toEqual({
      'source-1': 'portal-1',
    });
  });

  it('does not restore when the room or either child name changed', () => {
    const memory = rememberMappings({}, { 'source-1': 'portal-1' }, source, portal, 'room-1', '2026-07-13T00:00:00Z');

    expect(restoreRememberedMappings(memory, source, portal, 'room-2')).toEqual({});
    expect(restoreRememberedMappings(memory, [{ ...source[0], name: 'Different Child' }], portal, 'room-1')).toEqual({});
    expect(restoreRememberedMappings(memory, source, [{ ...portal[0], name: 'Different Child' }], 'room-1')).toEqual({});
  });

  it('restores multiple source records that were confirmed as the same portal child', () => {
    const duplicateSource = [
      ...source,
      { id: 'source-2', name: 'Shama Il Lamadeen duplicate' },
    ];
    const memory = rememberMappings(
      {},
      { 'source-1': 'portal-1', 'source-2': 'portal-1' },
      duplicateSource,
      portal,
      'room-1',
      '2026-07-13T00:00:00Z',
    );

    expect(restoreRememberedMappings(memory, duplicateSource, portal, 'room-1')).toEqual({
      'source-1': 'portal-1',
      'source-2': 'portal-1',
    });
  });

  it('removes stale and out-of-room mappings while preserving legitimate duplicate records', () => {
    expect(
      sanitizeActiveMappings(
        {
          'source-1': 'portal-1',
          'source-2': 'portal-outside',
          'source-outside': 'portal-2',
          'source-3': 'portal-1',
        },
        [
          { id: 'source-1', name: 'Child One' },
          { id: 'source-2', name: 'Child Two' },
          { id: 'source-3', name: 'Child Three' },
        ],
        [
          { id: 'portal-1', name: 'Child One' },
          { id: 'portal-2', name: 'Child Two' },
        ],
      ),
    ).toEqual({ 'source-1': 'portal-1', 'source-3': 'portal-1' });
  });
});

describe('durable denied AI recommendation memory', () => {
  const source = [{ id: 'source-1', name: 'Hekma Abas' }];
  const portals = [
    { id: 'portal-1', name: 'Hikma Abbas' },
    { id: 'portal-2', name: 'Hekma Abass' },
  ];
  const suggestion = {
    sourceChildId: 'source-1',
    portalChildId: 'portal-1',
    confidence: 0.94,
    reason: 'Likely spelling variation',
  };

  it('keeps a denied pair active for another monthly dataset with the same child and room', () => {
    const history = rememberDeniedSuggestion(
      [],
      suggestion,
      source,
      portals,
      'room-1',
      '2026-07-14T01:00:00Z',
    );

    expect(activeDeniedSuggestions(history, [...source], [...portals], 'room-1')).toEqual([
      expect.objectContaining({
        sourceChildId: 'source-1',
        sourceChildName: 'Hekma Abas',
        portalChildId: 'portal-1',
        portalChildName: 'Hikma Abbas',
      }),
    ]);
  });

  it('does not activate stale denials in another room or after either name changes', () => {
    const history = rememberDeniedSuggestion(
      [],
      suggestion,
      source,
      portals,
      'room-1',
      '2026-07-14T01:00:00Z',
    );

    expect(activeDeniedSuggestions(history, source, portals, 'room-2')).toEqual([]);
    expect(activeDeniedSuggestions(history, [{ ...source[0], name: 'Different Child' }], portals, 'room-1')).toEqual([]);
    expect(activeDeniedSuggestions(history, source, [{ ...portals[0], name: 'Different Child' }, portals[1]], 'room-1')).toEqual([]);
  });

  it('tracks exact pairs so the same source can reject more than one candidate', () => {
    const first = rememberDeniedSuggestion([], suggestion, source, portals, 'room-1', '2026-07-14T01:00:00Z');
    const second = rememberDeniedSuggestion(
      first,
      { ...suggestion, portalChildId: 'portal-2', confidence: 0.93 },
      source,
      portals,
      'room-1',
      '2026-07-14T02:00:00Z',
    );

    expect(activeDeniedSuggestions(second, source, portals, 'room-1')).toHaveLength(2);
    expect(activeDeniedSuggestions(second, source, portals, 'room-1').map((item) => item.portalChildId)).toEqual([
      'portal-2',
      'portal-1',
    ]);
  });

  it('clears the current room decisions once that source is mapped', () => {
    const currentRoom = rememberDeniedSuggestion([], suggestion, source, portals, 'room-1', '2026-07-14T01:00:00Z');
    const bothRooms = rememberDeniedSuggestion(currentRoom, suggestion, source, portals, 'room-2', '2026-07-14T02:00:00Z');

    expect(clearDeniedSources(bothRooms, ['source-1'], 'room-1')).toEqual([
      expect.objectContaining({ pageGroupId: 'room-2' }),
    ]);
  });
});
