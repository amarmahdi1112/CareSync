import { calculateSimilarity } from './levenshtein';
import { parseTimeSavrName, getDaysDifference } from './nameParser';
import type { ParsedName } from './nameParser';

export interface NameMatch {
  timeSavrName: string;
  portalName: string;
  matchedPortalId?: string;
  confidence: 'exact' | 'high' | 'medium' | 'low';
  score: number; // 0-1
  suggestManualReview: boolean;
  reason: string;
  dobMatch?: boolean;
  dobDaysDiff?: number;
  portalDob?: string;
  timeSavrDob?: string;
  enrollmentCategory?: string;
}

export interface PortalChild {
  id?: string;
  name: string;
  parsed: ParsedName;
  enrollmentCategory?: string;
  fullEnrollmentCategory?: string;
}

export interface MatchThresholds {
  exact: number;
  high: number;
  medium: number;
  low: number;
}

export interface TimeSavrRecord {
  name: string;
  dob?: string;
}

/**
 * Match TimeSavr names against Portal names
 */
export function matchNames(
  timeSavrRecords: (string | TimeSavrRecord)[],
  portalChildren: PortalChild[],
  thresholds: MatchThresholds = {
    exact: 0.98,
    high: 0.85,
    medium: 0.70,
    low: 0.50,
  }
): NameMatch[] {
  const results: NameMatch[] = [];

  for (const record of timeSavrRecords) {
    // Handle both string and object formats
    const timeSavrName = typeof record === 'string' ? record : record.name;
    const timeSavrDOB = typeof record === 'object' ? record.dob : undefined;
    
    const parsed = parseTimeSavrName(timeSavrName, timeSavrDOB);
    let bestMatch: NameMatch | null = null;
    let bestScore = 0;

    for (const portalChild of portalChildren) {
      const { score, dobMatch, dobDaysDiff } = calculateMatchScore(parsed, portalChild.parsed);

      if (score > bestScore) {
        bestScore = score;
        
        // Determine confidence level
        let confidence: 'exact' | 'high' | 'medium' | 'low';
        let reason: string;

        if (score >= thresholds.exact) {
          confidence = 'exact';
          reason = dobMatch 
            ? 'Exact name and DOB match' 
            : 'Exact or near-exact name match';
        } else if (score >= thresholds.high) {
          confidence = 'high';
          reason = dobMatch
            ? 'Strong name match with DOB confirmation'
            : dobDaysDiff !== undefined && dobDaysDiff <= 3
            ? `Strong name match (DOB off by ${dobDaysDiff} days)`
            : 'Strong fuzzy match';
        } else if (score >= thresholds.medium) {
          confidence = 'medium';
          reason = dobMatch
            ? 'Moderate name match but DOB confirms'
            : dobDaysDiff !== undefined && dobDaysDiff <= 7
            ? `Moderate name match (DOB off by ${dobDaysDiff} days)`
            : 'Moderate fuzzy match - review recommended';
        } else {
          confidence = 'low';
          reason = dobMatch
            ? 'Weak name match but DOB matches - verify names'
            : 'Weak match - manual review required';
        }

        bestMatch = {
          timeSavrName,
          portalName: portalChild.name,
          matchedPortalId: portalChild.id,
          confidence,
          score,
          suggestManualReview: score < thresholds.high && !dobMatch,
          reason,
          dobMatch,
          dobDaysDiff: dobDaysDiff !== undefined ? dobDaysDiff : undefined,
          portalDob: portalChild.parsed.dateOfBirth,
          timeSavrDob: parsed.dateOfBirth,
          enrollmentCategory: portalChild.enrollmentCategory,
        };
      }
    }

    if (bestMatch && bestScore >= thresholds.low) {
      results.push(bestMatch);
    } else {
      // No match found
      results.push({
        timeSavrName,
        portalName: '',
        confidence: 'low',
        score: 0,
        suggestManualReview: true,
        reason: 'No suitable match found - create new or manual assignment'
      });
    }
  }

  return results;
}

/**
 * Calculate match score between two parsed names
 */
function calculateMatchScore(
  name1: ParsedName, 
  name2: ParsedName
): { score: number; dobMatch: boolean; dobDaysDiff?: number } {
  // 1. Check normalized full name similarity (First + Last)
  const normalizedSimilarity = calculateSimilarity(name1.normalized, name2.normalized);

  // 2. Check first name similarity
  const firstNameSimilarity = calculateSimilarity(name1.firstName, name2.firstName);

  // 3. Check last name similarity
  const lastNameSimilarity = calculateSimilarity(name1.lastName, name2.lastName);

  // 4. Check middle name if both have it
  let middleNameBonus = 0;
  if (name1.middleName && name2.middleName) {
    const middleSimilarity = calculateSimilarity(name1.middleName, name2.middleName);
    middleNameBonus = middleSimilarity * 0.1; // 10% bonus
  }

  // 5. Date of Birth comparison - HUGE confidence boost
  let dobBonus = 0;
  let dobMatch = false;
  let dobDaysDiff: number | undefined = undefined;

  if (name1.dateOfBirth && name2.dateOfBirth) {
    const daysDiff = getDaysDifference(name1.dateOfBirth, name2.dateOfBirth);
    
    if (daysDiff !== null) {
      dobDaysDiff = daysDiff;
      
      if (daysDiff === 0) {
        // Exact DOB match - this is VERY strong evidence
        dobBonus = 0.25; // 25% bonus for exact DOB match
        dobMatch = true;
      } else if (daysDiff <= 1) {
        // Off by 1 day (possible timezone or data entry error)
        dobBonus = 0.20; // 20% bonus
        dobMatch = true;
      } else if (daysDiff <= 3) {
        // Off by 2-3 days (likely data entry error)
        dobBonus = 0.15; // 15% bonus
      } else if (daysDiff <= 7) {
        // Off by up to a week (possible error)
        dobBonus = 0.08; // 8% bonus
      } else if (daysDiff <= 30) {
        // Off by up to a month (might be typo in day)
        dobBonus = 0.03; // 3% bonus
      }
      // If more than 30 days off, no bonus
    }
  }

  // Weighted average with DOB boost
  // Base weights: normalized (35%), first (25%), last (25%), middle (bonus up to 10%)
  // DOB can add up to 25% more
  const baseScore = (
    normalizedSimilarity * 0.35 +
    firstNameSimilarity * 0.25 +
    lastNameSimilarity * 0.25 +
    middleNameBonus
  );

  const finalScore = Math.min(baseScore + dobBonus, 1); // Cap at 1

  return { score: finalScore, dobMatch, dobDaysDiff };
}
