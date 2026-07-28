/* eslint-disable @typescript-eslint/no-explicit-any */
import type { NameMatch } from '../algorithms/nameMatcher';
import { downloadCSV } from './csvParser';
import { saveApprovedNameMappings } from './localStorage';

/**
 * Generate CSV mapping content
 */
export function generateMappingCSV(matches: NameMatch[], reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>): string {
  // Generate CSV with DOB information and manual approval status
  const header = 'TimeSavr Name,Portal Name (Transformed),TimeSavr DOB,Portal DOB,Enrollment Category,Create New in Portal,Create New in TimeSavr,Direction,Confidence,Score %,DOB Match,DOB Days Diff,Manual Status,Action,Reason\n';
  
  // Forward matches (TimeSavr → Portal)
  const forwardRows = matches.map((match: any) => {
    const dobMatchStr = match.dobMatch ? 'Yes' : match.dobDaysDiff !== undefined ? 'Close' : 'N/A';
    const dobDaysStr = match.dobDaysDiff !== undefined ? match.dobDaysDiff : '';
    const manualStatus = match.manuallyApproved ? 'Approved' : match.rejected ? 'Rejected' : 'Auto';
    const createNewPortal = match.createNew ? 'YES' : 'NO';
    const action = match.createNew ? 'create_new' :
                   match.manuallyApproved || match.confidence === 'exact' || match.confidence === 'high' ? 'auto' : 
                   match.portalName && !match.rejected ? 'review' : 'create_new';
    const portalNameValue = match.portalName || '';
    const timeSavrDob = match.timeSavrDob || '';
    const portalDob = match.portalDob || '';
    const enrollmentCategory = match.enrollmentCategory || '';
    
    return `"${match.timeSavrName}","${portalNameValue}","${timeSavrDob}","${portalDob}","${enrollmentCategory}","${createNewPortal}","NO","TimeSavr→Portal","${match.confidence}",${Math.round(match.score * 100)},"${dobMatchStr}","${dobDaysStr}","${manualStatus}","${action}","${match.reason}"`;
  });

  // Reverse matches (Portal → TimeSavr)
  const reverseRows = (reverseMatches || []).map((match: any) => {
    return `"${match.timeSavrName}","${match.portalName}","${match.dob || ''}","${match.dob || ''}","","NO","YES","Portal→TimeSavr","exact",100,"Yes","0","Approved","create_timesavr","Create new TimeSavr record from unmatched Portal name"`;
  });

  const allRows = [...forwardRows, ...reverseRows].join('\n');
  return header + allRows;
}

/**
 * Export mapping to CSV file
 */
export function exportMappingToCSV(
  matches: NameMatch[], 
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>,
  filename: string = 'output-mapping.csv'
): void {
  const csv = generateMappingCSV(matches, reverseMatches);
  downloadCSV(csv, filename);
}

/**
 * Use portal name exactly as-is from CSV (no formatting)
 */
function useAsIs(name: string): string {
  return name ? name.trim() : '';
}

/**
 * Export approved portal names as PDF-ready sorted list
 */
export function exportApprovedNamesPDF(
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>
): void {
  // Save the approved name mappings to localStorage for use in claim reports
  saveApprovedNameMappings(matches, reverseMatches);
  
  // Get all approved matches (auto high confidence + manually approved)
  const approvedMatches = (matches as any[]).filter(m => 
    m.portalName && 
    !m.rejected && 
    (m.confidence === 'exact' || m.confidence === 'high' || m.manuallyApproved)
  );

  // Build data with portal names in "LastName, FirstName" format
  const approvedData = approvedMatches.map(m => ({
    portalName: m.portalName,
    originalName: m.timeSavrName,
    enrollmentCategory: m.enrollmentCategory || '',
    confidence: m.confidence,
  }));
  
  // Add reverse matches
  const reverseData = (reverseMatches || []).map(m => ({
    portalName: m.portalName,
    originalName: m.timeSavrName,
    enrollmentCategory: '',
    confidence: 'exact',
  }));
  
  // Combine and sort alphabetically by portal name (ascending)
  const allData = [...approvedData, ...reverseData]
    .filter(d => d.portalName)
    .sort((a, b) => a.portalName.localeCompare(b.portalName, undefined, { sensitivity: 'base' }));

  // Remove duplicates by portal name
  const uniqueData = allData.filter((item, index, self) => 
    index === self.findIndex(t => t.portalName === item.portalName)
  );

  // Generate printable HTML with table format
  const tableRows = uniqueData.map((item, idx) => `
    <tr>
      <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: center; color: #6b7280;">${idx + 1}</td>
      <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; font-weight: 600;">${item.portalName}</td>
      <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; color: #6b7280; font-size: 11px;">${item.originalName}</td>
      <td style="padding: 8px 12px; border-bottom: 1px solid #e5e7eb; text-align: center;">
        ${item.enrollmentCategory ? `<span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 10px;">${item.enrollmentCategory}</span>` : '-'}
      </td>
    </tr>
  `).join('');

  const printContent = `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Approved Portal Names - Claim Report</title>
      <style>
        @page {
          margin: 0.5in;
          size: letter portrait;
        }
        * {
          box-sizing: border-box;
        }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          font-size: 12px;
          line-height: 1.4;
          color: #1f2937;
          margin: 0;
          padding: 20px;
        }
        .header {
          border-bottom: 3px solid #1e40af;
          padding-bottom: 16px;
          margin-bottom: 20px;
        }
        .header h1 {
          font-size: 22px;
          margin: 0 0 4px 0;
          color: #1e40af;
        }
        .header .subtitle {
          font-size: 12px;
          color: #6b7280;
        }
        .stats {
          display: flex;
          gap: 30px;
          margin-bottom: 20px;
          padding: 12px 16px;
          background: #f8fafc;
          border-radius: 8px;
        }
        .stat {
          text-align: center;
        }
        .stat-value {
          font-size: 24px;
          font-weight: bold;
          color: #059669;
        }
        .stat-label {
          font-size: 10px;
          color: #6b7280;
          text-transform: uppercase;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
        }
        thead th {
          background: #1e40af;
          color: white;
          padding: 10px 12px;
          text-align: left;
          font-weight: 600;
          text-transform: uppercase;
          font-size: 10px;
          letter-spacing: 0.5px;
        }
        thead th.center { text-align: center; }
        tbody tr:nth-child(even) {
          background: #f9fafb;
        }
        tbody tr:hover {
          background: #f3f4f6;
        }
        .footer {
          margin-top: 20px;
          padding-top: 12px;
          border-top: 1px solid #e5e7eb;
          font-size: 10px;
          color: #9ca3af;
          text-align: center;
        }
        .note {
          background: #fef3c7;
          border: 1px solid #fbbf24;
          border-radius: 6px;
          padding: 10px 14px;
          margin-bottom: 16px;
          font-size: 11px;
          color: #92400e;
        }
        @media print {
          body { padding: 0; }
          .no-print { display: none; }
        }
      </style>
    </head>
    <body>
      <div class="header">
        <h1>Approved Portal Names</h1>
        <div class="subtitle">Name Sync Report • Generated ${new Date().toLocaleString()}</div>
      </div>
      
      <div class="stats">
        <div class="stat">
          <div class="stat-value">${uniqueData.length}</div>
          <div class="stat-label">Total Approved</div>
        </div>
        <div class="stat">
          <div class="stat-value">${approvedData.length}</div>
          <div class="stat-label">Matched Names</div>
        </div>
        <div class="stat">
          <div class="stat-value">${reverseData.length}</div>
          <div class="stat-label">Reverse Matches</div>
        </div>
      </div>

      <div class="note">
        <strong>📋 Portal Format:</strong> Names are displayed exactly as they appear in the CSV.
      </div>

      <table>
        <thead>
          <tr>
            <th class="center" style="width: 50px;">#</th>
            <th>Portal Name</th>
            <th>Original Claim Name</th>
            <th class="center" style="width: 120px;">Category</th>
          </tr>
        </thead>
        <tbody>
          ${tableRows}
        </tbody>
      </table>

      <div class="footer">
        CareSync Name Sync Tool • ${uniqueData.length} approved names • Sorted A-Z by Portal Name
      </div>
    </body>
    </html>
  `;

  // Open print window
  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(printContent);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => printWindow.print(), 250);
  }
}

/**
 * Export approved PORTAL names as CSV (sorted alphabetically)
 * This exports ONLY the portal names - ready to use for claims
 */
export function exportApprovedNamesCSV(
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>
): void {
  // Save mappings first
  saveApprovedNameMappings(matches, reverseMatches);
  
  // Get all approved matches
  const approvedMatches = (matches as any[]).filter(m => 
    m.portalName && 
    !m.rejected && 
    (m.confidence === 'exact' || m.confidence === 'high' || m.manuallyApproved)
  );

  // Get portal names
  const portalNames = approvedMatches.map(m => m.portalName);

  // Add reverse matches portal names
  const reversePortalNames = (reverseMatches || []).map(m => m.portalName);

  // Combine, remove duplicates, and sort alphabetically
  const allPortalNames = [...new Set([...portalNames, ...reversePortalNames])]
    .filter(name => name)
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));

  // Generate simple CSV - just portal names (for easy use)
  const header = 'Portal Name\n';
  const csvRows = allPortalNames.map(name => `"${name}"`).join('\n');
  
  downloadCSV(header + csvRows, 'portal-names-sorted.csv');
}

/**
 * Export full mapping CSV with both portal and original names
 */
export function exportFullMappingCSV(
  matches: NameMatch[],
  reverseMatches?: Array<{ portalName: string; timeSavrName: string; dob?: string }>
): void {
  // Save mappings first
  saveApprovedNameMappings(matches, reverseMatches);
  
  // Get all approved matches
  const approvedMatches = (matches as any[]).filter(m => 
    m.portalName && 
    !m.rejected && 
    (m.confidence === 'exact' || m.confidence === 'high' || m.manuallyApproved)
  );

  // Get portal names with their details
  const rows = approvedMatches.map(m => ({
    portalName: m.portalName,
    originalName: m.timeSavrName,
    confidence: m.confidence,
    enrollmentCategory: m.enrollmentCategory || '',
  }));

  // Add reverse matches
  const reverseRows = (reverseMatches || []).map(m => ({
    portalName: useAsIs(m.portalName),
    originalName: m.timeSavrName,
    confidence: 'exact',
    enrollmentCategory: '',
  }));

  // Combine and sort alphabetically by portal name
  const allRows = [...rows, ...reverseRows]
    .filter(r => r.portalName)
    .sort((a, b) => a.portalName.localeCompare(b.portalName, undefined, { sensitivity: 'base' }));

  // Generate CSV with both names
  const header = 'Portal Name,Original TimeSavr Name,Confidence,Enrollment Category\n';
  const csvRows = allRows.map(r => 
    `"${r.portalName}","${r.originalName}","${r.confidence}","${r.enrollmentCategory}"`
  ).join('\n');
  
  downloadCSV(header + csvRows, 'name-mapping-full.csv');
}

/**
 * Export filtered results
 */
export function exportFilteredResults(
  matches: NameMatch[],
  filter: 'auto' | 'review' | 'exact' | 'high' | 'medium' | 'low' | 'no-match'
): void {
  let filtered: NameMatch[];
  let filename: string;
  
  switch (filter) {
    case 'auto':
      filtered = matches.filter(m => m.confidence === 'exact' || m.confidence === 'high');
      filename = 'auto-transform.csv';
      break;
    case 'review':
      filtered = matches.filter(m => m.suggestManualReview);
      filename = 'needs-review.csv';
      break;
    case 'exact':
      filtered = matches.filter(m => m.confidence === 'exact');
      filename = 'exact-matches.csv';
      break;
    case 'high':
      filtered = matches.filter(m => m.confidence === 'high');
      filename = 'high-confidence.csv';
      break;
    case 'medium':
      filtered = matches.filter(m => m.confidence === 'medium');
      filename = 'medium-confidence.csv';
      break;
    case 'low':
      filtered = matches.filter(m => m.confidence === 'low');
      filename = 'low-confidence.csv';
      break;
    case 'no-match':
      filtered = matches.filter(m => !m.portalName);
      filename = 'no-match.csv';
      break;
    default:
      filtered = matches;
      filename = 'filtered-results.csv';
  }
  
  const csv = generateMappingCSV(filtered);
  downloadCSV(csv, filename);
}

/**
 * Generate statistics summary
 */
export function generateSummary(matches: NameMatch[]): {
  total: number;
  exact: number;
  high: number;
  medium: number;
  low: number;
  noMatch: number;
  autoTransform: number;
  needsReview: number;
  manuallyApproved: number;
  rejected: number;
} {
  const matchesWithApproval = matches as any[];
  
  const exact = matchesWithApproval.filter(m => m.confidence === 'exact' && !m.manuallyApproved).length;
  const high = matchesWithApproval.filter(m => m.confidence === 'high').length;
  const medium = matchesWithApproval.filter(m => m.confidence === 'medium').length;
  const low = matchesWithApproval.filter(m => m.confidence === 'low' && !m.rejected).length;
  const noMatch = matchesWithApproval.filter(m => !m.portalName && !m.rejected).length;
  const manuallyApproved = matchesWithApproval.filter(m => m.manuallyApproved).length;
  const rejected = matchesWithApproval.filter(m => m.rejected).length;

  return {
    total: matches.length,
    exact,
    high,
    medium,
    low,
    noMatch,
    autoTransform: exact + high + manuallyApproved,
    needsReview: medium + low + noMatch,
    manuallyApproved,
    rejected,
  };
}

