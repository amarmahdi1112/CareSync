import { parsePortalName } from '../algorithms/nameParser';
import type { PortalChild } from '../algorithms/nameMatcher';

/**
 * Parse Portal CSV with format: Last Name,First Name,Enrolment Category,Date of birth
 */
export function parsePortalCSV(content: string): PortalChild[] {
  const lines = content.split('\n').filter(line => line.trim());
  
  if (lines.length === 0) {
    return [];
  }

  // Skip header row
  const startIndex = 1;
  const children: PortalChild[] = [];
  
  for (let i = startIndex; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    
    try {
      // Parse CSV line (handle quotes)
      const columns = parseCSVLine(line);
      
      if (columns.length >= 4) {
        const lastName = columns[0].trim();
        const firstName = columns[1].trim();
        const enrollmentCategory = columns[2].trim();
        const dateOfBirth = columns[3].trim();
        
        // Extract care type (Daycare or Out-of-school care)
        let careType = '';
        if (enrollmentCategory.toLowerCase().includes('daycare')) {
          careType = 'Daycare';
        } else if (enrollmentCategory.toLowerCase().includes('out-of-school')) {
          careType = 'Out-of-school care';
        }
        
        // Combine to "Last, First" format
        const fullName = `${lastName}, ${firstName}`;
        
        if (lastName && firstName) {
          children.push({
            id: `portal-${i}`,
            name: fullName,
            parsed: parsePortalName(fullName, dateOfBirth),
            enrollmentCategory: careType,
            fullEnrollmentCategory: enrollmentCategory,
          });
        }
      }
    } catch (error) {
      console.warn(`Error parsing Portal line ${i}:`, line, error);
    }
  }
  
  return children;
}

/**
 * Parse TimeSavr CSV with format: ID,Child Name,Start Date,End Date,Birthdate,...
 */
export function parseTimeSavrCSV(content: string): Array<{ name: string; dob?: string }> {
  const lines = content.split('\n').filter(line => line.trim());
  
  if (lines.length === 0) {
    return [];
  }

  // Skip header row
  const startIndex = 1;
  const names: Array<{ name: string; dob?: string }> = [];
  
  for (let i = startIndex; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    
    try {
      // Parse CSV line (handle quotes)
      const columns = parseCSVLine(line);
      
      if (columns.length >= 5) {
        const childName = columns[1].trim();
        const birthdate = columns[4].trim();
        
        if (childName) {
          names.push({
            name: childName,
            dob: birthdate
          });
        }
      }
    } catch (error) {
      console.warn(`Error parsing TimeSavr line ${i}:`, line, error);
    }
  }
  
  return names;
}

/**
 * Parse a CSV line handling quoted fields
 */
function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  
  // Add the last field
  result.push(current);
  
  return result;
}

/**
 * Read file as text
 */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      const text = e.target?.result as string;
      resolve(text);
    };
    
    reader.onerror = () => {
      reject(new Error('Failed to read file'));
    };
    
    reader.readAsText(file);
  });
}

/**
 * Download content as CSV file
 */
export function downloadCSV(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  URL.revokeObjectURL(url);
}
