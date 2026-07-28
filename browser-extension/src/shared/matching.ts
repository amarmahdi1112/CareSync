import type {
  AiDeniedSuggestion,
  AiNameSuggestion,
  ChildMappingMemory,
  PortalChild,
  SourceChild,
} from './types';

const MAX_DENIED_SUGGESTIONS = 2_000;

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function parsedDeniedSuggestions(value: unknown): AiDeniedSuggestion[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((candidate) => {
    if (!isObject(candidate)) return [];
    const confidence = Number(candidate.confidence);
    const denied: AiDeniedSuggestion = {
      sourceChildId: String(candidate.sourceChildId ?? '').trim(),
      sourceChildName: String(candidate.sourceChildName ?? '').trim(),
      portalChildId: String(candidate.portalChildId ?? '').trim(),
      portalChildName: String(candidate.portalChildName ?? '').trim(),
      pageGroupId: String(candidate.pageGroupId ?? '').trim(),
      confidence,
      reason: String(candidate.reason ?? '').slice(0, 300),
      deniedAt: String(candidate.deniedAt ?? '').trim(),
    };
    if (
      !denied.sourceChildId ||
      !denied.sourceChildName ||
      !denied.portalChildId ||
      !denied.portalChildName ||
      !denied.pageGroupId ||
      !denied.deniedAt ||
      !Number.isFinite(confidence) ||
      confidence < 0 ||
      confidence > 1
    ) return [];
    return [denied];
  });
}

function deniedKey(value: Pick<AiDeniedSuggestion, 'pageGroupId' | 'sourceChildId' | 'portalChildId'>): string {
  return `${value.pageGroupId}\u0000${value.sourceChildId}\u0000${value.portalChildId}`;
}

export function normalizeName(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('en-CA')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function nameTokenKey(value: string): string {
  return normalizeName(value).split(' ').filter(Boolean).sort().join(' ');
}

/**
 * Return source -> portal mappings only when the visible portal roster has one
 * exact normalized or exact token-order-independent candidate.
 */
export function exactSourceMappings(
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
): Record<string, string> {
  const byToken = new Map<string, PortalChild[]>();
  for (const portalChild of portalChildren) {
    const tokenKey = nameTokenKey(portalChild.name);
    byToken.set(tokenKey, [...(byToken.get(tokenKey) || []), portalChild]);
  }

  const mappings: Record<string, string> = {};
  for (const sourceChild of sourceChildren) {
    const matches = byToken.get(nameTokenKey(sourceChild.name)) || [];
    if (matches.length === 1) mappings[sourceChild.id] = matches[0].id;
  }
  return mappings;
}

export interface AutoMappingResult {
  mappings: Record<string, string>;
  ambiguousPortalChildIds: string[];
  unmatchedPortalChildIds: string[];
}

export function autoMapChildren(portalChildren: PortalChild[], sourceChildren: SourceChild[]): AutoMappingResult {
  const mappings: Record<string, string> = {};
  const ambiguousPortalChildIds: string[] = [];
  const unmatchedPortalChildIds: string[] = [];
  const alreadyUsed = new Set<string>();

  for (const portalChild of portalChildren) {
    const normalized = normalizeName(portalChild.name);
    let candidates = sourceChildren.filter((child) => normalizeName(child.name) === normalized);
    if (candidates.length === 0) {
      const tokenKey = nameTokenKey(portalChild.name);
      candidates = sourceChildren.filter((child) => nameTokenKey(child.name) === tokenKey);
    }
    candidates = candidates.filter((child) => !alreadyUsed.has(child.id));
    if (candidates.length === 1) {
      mappings[portalChild.id] = candidates[0].id;
      alreadyUsed.add(candidates[0].id);
    } else if (candidates.length > 1) {
      ambiguousPortalChildIds.push(portalChild.id);
    } else {
      unmatchedPortalChildIds.push(portalChild.id);
    }
  }
  return { mappings, ambiguousPortalChildIds, unmatchedPortalChildIds };
}

export function rememberMappings(
  memory: Record<string, ChildMappingMemory>,
  mappings: Record<string, string>,
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
  pageGroupId: string,
  savedAt: string,
): Record<string, ChildMappingMemory> {
  const next = { ...memory };
  const sourcesById = new Map(sourceChildren.map((child) => [child.id, child]));
  const portalsById = new Map(portalChildren.map((child) => [child.id, child]));
  for (const [sourceId, portalId] of Object.entries(mappings)) {
    const source = sourcesById.get(sourceId);
    const portal = portalsById.get(portalId);
    if (!source || !portal || !pageGroupId) continue;
    next[sourceId] = {
      sourceId,
      sourceName: source.name,
      portalId,
      portalName: portal.name,
      pageGroupId,
      savedAt,
    };
  }
  return next;
}

export function restoreRememberedMappings(
  memory: Record<string, ChildMappingMemory>,
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
  pageGroupId: string,
): Record<string, string> {
  const mappings: Record<string, string> = {};
  const portalsById = new Map(portalChildren.map((child) => [child.id, child]));
  for (const source of sourceChildren) {
    const remembered = memory[source.id];
    const portal = remembered ? portalsById.get(remembered.portalId) : undefined;
    if (
      !remembered ||
      !portal ||
      remembered.pageGroupId !== pageGroupId ||
      normalizeName(remembered.sourceName) !== normalizeName(source.name) ||
      normalizeName(remembered.portalName) !== normalizeName(portal.name)
    ) {
      continue;
    }
    mappings[source.id] = portal.id;
  }
  return mappings;
}

export function sanitizeActiveMappings(
  mappings: Record<string, string>,
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
): Record<string, string> {
  const sourceIds = new Set(sourceChildren.map((child) => child.id));
  const portalIds = new Set(portalChildren.map((child) => child.id));
  const sanitized: Record<string, string> = {};
  for (const [sourceId, portalId] of Object.entries(mappings)) {
    if (!sourceIds.has(sourceId) || !portalIds.has(portalId)) continue;
    sanitized[sourceId] = portalId;
  }
  return sanitized;
}

/**
 * Return only denials that still describe the current ZIP child, portal child,
 * and room. This prevents stale records from suppressing a legitimate match.
 */
export function activeDeniedSuggestions(
  history: unknown,
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
  pageGroupId: string,
): AiDeniedSuggestion[] {
  const sourcesById = new Map(sourceChildren.map((child) => [child.id, child]));
  const portalsById = new Map(portalChildren.map((child) => [child.id, child]));
  const byPair = new Map<string, AiDeniedSuggestion>();
  for (const denied of parsedDeniedSuggestions(history)) {
    const source = sourcesById.get(denied.sourceChildId);
    const portal = portalsById.get(denied.portalChildId);
    if (
      denied.pageGroupId !== pageGroupId ||
      !source ||
      !portal ||
      normalizeName(denied.sourceChildName) !== normalizeName(source.name) ||
      normalizeName(denied.portalChildName) !== normalizeName(portal.name)
    ) continue;
    const key = deniedKey(denied);
    const existing = byPair.get(key);
    if (!existing || existing.deniedAt <= denied.deniedAt) byPair.set(key, denied);
  }
  return [...byPair.values()].sort((left, right) => right.deniedAt.localeCompare(left.deniedAt));
}

/** Persist one exact rejected pair while retaining decisions from other rooms. */
export function rememberDeniedSuggestion(
  history: unknown,
  suggestion: AiNameSuggestion,
  sourceChildren: SourceChild[],
  portalChildren: PortalChild[],
  pageGroupId: string,
  deniedAt: string,
): AiDeniedSuggestion[] {
  const source = sourceChildren.find((child) => child.id === suggestion.sourceChildId);
  const portal = portalChildren.find((child) => child.id === suggestion.portalChildId);
  const confidence = Number(suggestion.confidence);
  if (
    !source ||
    !portal ||
    !pageGroupId ||
    !Number.isFinite(confidence) ||
    confidence < 0 ||
    confidence > 1
  ) return parsedDeniedSuggestions(history);
  const denied: AiDeniedSuggestion = {
    sourceChildId: source.id,
    sourceChildName: source.name,
    portalChildId: portal.id,
    portalChildName: portal.name,
    pageGroupId,
    confidence,
    reason: String(suggestion.reason || 'Possible name variation').slice(0, 300),
    deniedAt,
  };
  const next = parsedDeniedSuggestions(history).filter((candidate) => deniedKey(candidate) !== deniedKey(denied));
  return [...next, denied]
    .sort((left, right) => left.deniedAt.localeCompare(right.deniedAt))
    .slice(-MAX_DENIED_SUGGESTIONS);
}

/** Remove obsolete denials once the operator maps those sources in this room. */
export function clearDeniedSources(
  history: unknown,
  sourceIds: Iterable<string>,
  pageGroupId: string,
): AiDeniedSuggestion[] {
  const resolved = new Set(sourceIds);
  return parsedDeniedSuggestions(history).filter(
    (denied) => denied.pageGroupId !== pageGroupId || !resolved.has(denied.sourceChildId),
  );
}
