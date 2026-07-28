export interface ParsedName {
  firstName: string;
  lastName: string;
  middleName?: string;
  fullName: string;
  normalized: string; // lowercase, no punctuation
  dateOfBirth?: string; // ISO format date
}

/**
 * Parse name from "Last, First Middle" format (Portal format)
 */
export function parsePortalName(name: string, dob?: string): ParsedName {
  const trimmed = name.trim();
  
  // Check if comma-separated (Last, First Middle)
  if (trimmed.includes(',')) {
    const [lastPart, firstPart] = trimmed.split(',').map(s => s.trim());
    const firstNames = firstPart.split(/\s+/);
    
    return {
      firstName: firstNames[0] || '',
      lastName: lastPart || '',
      middleName: firstNames.slice(1).join(' ') || undefined,
      fullName: name,
      normalized: normalizeString(`${firstNames[0]} ${lastPart}`),
      dateOfBirth: dob ? normalizeDateOfBirth(dob) : undefined,
    };
  }
  
  // Space-separated (First Last or First Middle Last)
  const parts = trimmed.split(/\s+/);
  return {
    firstName: parts[0] || '',
    lastName: parts[parts.length - 1] || '',
    middleName: parts.slice(1, -1).join(' ') || undefined,
    fullName: name,
    normalized: normalizeString(`${parts[0]} ${parts[parts.length - 1]}`),
    dateOfBirth: dob ? normalizeDateOfBirth(dob) : undefined,
  };
}

/**
 * Parse TimeSavr name (could be "First Last", "LAST FIRST", etc.)
 */
export function parseTimeSavrName(name: string, dob?: string): ParsedName {
  const trimmed = name.trim();
  
  // If all caps and comma-separated, likely "LAST, FIRST"
  if (trimmed === trimmed.toUpperCase() && trimmed.includes(',')) {
    const [lastPart, firstPart] = trimmed.split(',').map(s => s.trim());
    return {
      firstName: toTitleCase(firstPart.split(/\s+/)[0]),
      lastName: toTitleCase(lastPart),
      middleName: firstPart.split(/\s+/).slice(1).join(' ') || undefined,
      fullName: name,
      normalized: normalizeString(`${firstPart.split(/\s+/)[0]} ${lastPart}`),
      dateOfBirth: dob ? normalizeDateOfBirth(dob) : undefined,
    };
  }
  
  // Otherwise assume "First Last" or "First Middle Last"
  const parts = trimmed.split(/\s+/);
  return {
    firstName: toTitleCase(parts[0] || ''),
    lastName: toTitleCase(parts[parts.length - 1] || ''),
    middleName: parts.slice(1, -1).join(' ') || undefined,
    fullName: name,
    normalized: normalizeString(`${parts[0]} ${parts[parts.length - 1]}`),
    dateOfBirth: dob ? normalizeDateOfBirth(dob) : undefined,
  };
}

/**
 * Normalize string for comparison (lowercase, remove punctuation, trim)
 */
export function normalizeString(str: string): string {
  return str
    .toLowerCase()
    .replace(/[-.,/#!$%^&*;:{}=_`~()]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Normalize date of birth to ISO format (YYYY-MM-DD)
 */
export function normalizeDateOfBirth(dob: string): string | undefined {
  if (!dob || dob === '0000-00-00') return undefined;
  
  try {
    // Handle "18 Jun 2023" format
    const ddMmmYyyy = /^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$/;
    const match = dob.trim().match(ddMmmYyyy);
    
    if (match) {
      const [, day, monthStr, year] = match;
      const monthMap: { [key: string]: string } = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
      };
      const month = monthMap[monthStr];
      if (month) {
        const paddedDay = day.padStart(2, '0');
        return `${year}-${month}-${paddedDay}`;
      }
    }
    
    // Handle various other date formats
    const date = new Date(dob);
    if (isNaN(date.getTime())) return undefined;
    
    // Return ISO format
    return date.toISOString().split('T')[0];
  } catch {
    return undefined;
  }
}

/**
 * Calculate days difference between two dates
 */
export function getDaysDifference(date1?: string, date2?: string): number | null {
  if (!date1 || !date2) return null;
  
  try {
    const d1 = new Date(date1);
    const d2 = new Date(date2);
    
    if (isNaN(d1.getTime()) || isNaN(d2.getTime())) return null;
    
    const diffTime = Math.abs(d2.getTime() - d1.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    return diffDays;
  } catch {
    return null;
  }
}

/**
 * Convert to Title Case
 */
function toTitleCase(str: string): string {
  return str
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
