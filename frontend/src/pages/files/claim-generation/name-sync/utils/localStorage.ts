/* eslint-disable @typescript-eslint/no-explicit-any */
import type { NameMatch } from '../algorithms/nameMatcher';

const STORAGE_KEY = 'name-sync-history';
const NAME_MAPPING_KEY = 'approved-name-mappings';
const MAX_HISTORY = 10;

/**
 * Name mapping for claim reports - maps original claim name to approved portal name
 */
export interface NameMapping {
  originalName: string;
  portalName: string;  // In "LastName, FirstName" format
  confidence: string;
  approved: boolean;
}

/**
 * Save approved name mappings for use in claim report exports
 */
export function saveApprovedNameMappings(
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string }>
): void {
  try {
    const mappings: NameMapping[] = [];
    
    // Add approved forward matches
    (matches as any[]).forEach(m => {
      if (m.portalName && !m.rejected && 
          (m.confidence === 'exact' || m.confidence === 'high' || m.manuallyApproved)) {
        mappings.push({
          originalName: m.timeSavrName,
          portalName: m.portalName,
          confidence: m.confidence,
          approved: true,
        });
      }
    });
    
    // Add reverse matches
    (reverseMatches || []).forEach(m => {
      mappings.push({
        originalName: m.timeSavrName,
        portalName: m.portalName,
        confidence: 'exact',
        approved: true,
      });
    });
    
    localStorage.setItem(NAME_MAPPING_KEY, JSON.stringify(mappings));
  } catch (error) {
    console.error('Failed to save name mappings:', error);
  }
}

/**
 * Get approved name mappings
 */
export function getApprovedNameMappings(): NameMapping[] {
  try {
    const data = localStorage.getItem(NAME_MAPPING_KEY);
    if (!data) return [];
    return JSON.parse(data) as NameMapping[];
  } catch (error) {
    console.error('Failed to load name mappings:', error);
    return [];
  }
}

/**
 * Get portal name for a given original claim name
 * Returns the portal name exactly as-is from CSV if found, otherwise returns original name
 */
export function getPortalName(originalName: string): string {
  const mappings = getApprovedNameMappings();
  
  // Try exact match first
  const exactMatch = mappings.find(m => 
    m.originalName.toLowerCase() === originalName.toLowerCase()
  );
  if (exactMatch) return exactMatch.portalName;
  
  // Try partial match (in case of slight differences)
  const partialMatch = mappings.find(m => 
    m.originalName.toLowerCase().includes(originalName.toLowerCase()) ||
    originalName.toLowerCase().includes(m.originalName.toLowerCase())
  );
  if (partialMatch) return partialMatch.portalName;
  
  // Return original name as-is if no mapping found
  return originalName;
}

/**
 * Normalize a name for comparison - handles both "FirstName LastName" and "LastName, FirstName" formats
 */
function normalizeName(name: string): string {
  const trimmed = name.trim().toLowerCase();
  if (trimmed.includes(',')) {
    // "LastName, FirstName" -> extract parts
    const parts = trimmed.split(',').map(p => p.trim());
    return parts.join(' '); // "lastname firstname"
  }
  return trimmed;
}

/**
 * Get full name mapping (both claim name and portal name) for a given name
 * Primary lookup is by Portal Name since that's how children are identified in the system
 * Returns { claimName, portalName } or null if no mapping found
 */
export function getNameMapping(searchName: string): { claimName: string; portalName: string } | null {
  const mappings = getApprovedNameMappings();
  const searchLower = searchName.toLowerCase().trim();
  const searchNormalized = normalizeName(searchName);
  
  // PRIORITY 1: Exact match on portal name (primary identifier)
  let match = mappings.find(m => m.portalName.toLowerCase().trim() === searchLower);
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  // PRIORITY 2: Normalized match on portal name (handles format differences)
  match = mappings.find(m => normalizeName(m.portalName) === searchNormalized);
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  // PRIORITY 3: Exact match on claim name
  match = mappings.find(m => m.originalName.toLowerCase().trim() === searchLower);
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  // PRIORITY 4: Normalized match on claim name
  match = mappings.find(m => normalizeName(m.originalName) === searchNormalized);
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  // PRIORITY 5: Partial match on portal name
  match = mappings.find(m => {
    const portalLower = m.portalName.toLowerCase();
    return portalLower.includes(searchLower) || searchLower.includes(portalLower);
  });
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  // PRIORITY 6: Partial match on claim name
  match = mappings.find(m => {
    const claimLower = m.originalName.toLowerCase();
    return claimLower.includes(searchLower) || searchLower.includes(claimLower);
  });
  if (match) return { claimName: match.originalName, portalName: match.portalName };
  
  return null;
}

/**
 * Clear name mappings
 */
export function clearNameMappings(): void {
  try {
    localStorage.removeItem(NAME_MAPPING_KEY);
  } catch (error) {
    console.error('Failed to clear name mappings:', error);
  }
}

export interface MatchHistory {
  id: string;
  timestamp: number;
  portalCount: number;
  timeSavrCount: number;
  matches: NameMatch[];
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>;
  summary: {
    exact: number;
    high: number;
    medium: number;
    low: number;
    noMatch: number;
    manuallyApproved?: number;
    rejected?: number;
  };
}

/**
 * Save match results to localStorage
 */
export function saveToHistory(
  portalCount: number,
  timeSavrCount: number,
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>
): string {
  try {
    const history = getHistory();
    const matchesWithApproval = matches as any[];
    
    const summary = {
      exact: matchesWithApproval.filter(m => m.confidence === 'exact').length,
      high: matchesWithApproval.filter(m => m.confidence === 'high').length,
      medium: matchesWithApproval.filter(m => m.confidence === 'medium').length,
      low: matchesWithApproval.filter(m => m.confidence === 'low').length,
      noMatch: matchesWithApproval.filter(m => !m.portalName).length,
      manuallyApproved: matchesWithApproval.filter(m => m.manuallyApproved).length,
      rejected: matchesWithApproval.filter(m => m.rejected).length,
    };
    
    const id = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newEntry: MatchHistory = {
      id,
      timestamp: Date.now(),
      portalCount,
      timeSavrCount,
      matches,
      reverseMatches,
      summary,
    };
    
    // Add to beginning of array
    history.unshift(newEntry);
    
    // Keep only the last MAX_HISTORY entries
    const trimmedHistory = history.slice(0, MAX_HISTORY);
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmedHistory));
    return id;
  } catch (error) {
    console.error('Failed to save to history:', error);
    return '';
  }
}

/**
 * Update an existing history entry with new matches (preserves approval states)
 */
export function updateHistoryEntry(
  id: string,
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>
): void {
  try {
    const history = getHistory();
    const index = history.findIndex(entry => entry.id === id);
    
    if (index === -1) return;
    
    const matchesWithApproval = matches as any[];
    
    history[index].matches = matches;
    history[index].reverseMatches = reverseMatches;
    history[index].timestamp = Date.now();
    history[index].summary = {
      exact: matchesWithApproval.filter(m => m.confidence === 'exact').length,
      high: matchesWithApproval.filter(m => m.confidence === 'high').length,
      medium: matchesWithApproval.filter(m => m.confidence === 'medium').length,
      low: matchesWithApproval.filter(m => m.confidence === 'low').length,
      noMatch: matchesWithApproval.filter(m => !m.portalName).length,
      manuallyApproved: matchesWithApproval.filter(m => m.manuallyApproved).length,
      rejected: matchesWithApproval.filter(m => m.rejected).length,
    };
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (error) {
    console.error('Failed to update history entry:', error);
  }
}

/**
 * Save current work in progress (auto-save)
 */
export function saveWorkInProgress(
  matches: NameMatch[],
  reverseMatches: Array<{ portalName: string; timeSavrName: string; dob?: string }>,
  portalData: any[],
  timeSavrNames: string[]
): void {
  try {
    const wipData = {
      matches,
      reverseMatches,
      portalData,
      timeSavrNames,
      timestamp: Date.now(),
    };
    localStorage.setItem('name-sync-wip', JSON.stringify(wipData));
  } catch (error) {
    console.error('Failed to save work in progress:', error);
  }
}

/**
 * Load work in progress
 */
export function loadWorkInProgress(): {
  matches: NameMatch[];
  reverseMatches: Array<{ portalName: string; timeSavrName: string; dob?: string }>;
  portalData: any[];
  timeSavrNames: string[];
  timestamp: number;
} | null {
  try {
    const data = localStorage.getItem('name-sync-wip');
    if (!data) return null;
    return JSON.parse(data);
  } catch (error) {
    console.error('Failed to load work in progress:', error);
    return null;
  }
}

/**
 * Clear work in progress
 */
export function clearWorkInProgress(): void {
  try {
    localStorage.removeItem('name-sync-wip');
  } catch (error) {
    console.error('Failed to clear work in progress:', error);
  }
}

/**
 * Get match history from localStorage
 */
export function getHistory(): MatchHistory[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return [];
    
    return JSON.parse(data) as MatchHistory[];
  } catch (error) {
    console.error('Failed to load history:', error);
    return [];
  }
}

/**
 * Clear match history
 */
export function clearHistory(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Failed to clear history:', error);
  }
}

/**
 * Get specific history entry by ID
 */
export function getHistoryById(id: string): MatchHistory | null {
  const history = getHistory();
  return history.find(entry => entry.id === id) || null;
}

/**
 * Delete specific history entry
 */
export function deleteHistoryEntry(id: string): void {
  try {
    const history = getHistory();
    const filtered = history.filter(entry => entry.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
  } catch (error) {
    console.error('Failed to delete history entry:', error);
  }
}

