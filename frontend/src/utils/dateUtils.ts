// ============================================
// Date Utility Functions
// Shared date parsing and formatting across the app
// ============================================

/**
 * Safely parse a timestamp into a Date object
 * Handles: string dates, numeric strings, numeric timestamps (seconds or ms), null/undefined
 */
export const parseTimestamp = (timestamp: string | number | null | undefined): Date | null => {
  if (!timestamp) return null;
  
  let date: Date;
  
  // Check if it's a numeric string like "1764791126387"
  if (typeof timestamp === 'string' && /^\d+$/.test(timestamp)) {
    const numericValue = parseInt(timestamp, 10);
    // If it's a small number, it's likely Unix seconds - convert to ms
    date = new Date(numericValue < 10000000000 ? numericValue * 1000 : numericValue);
  } else if (typeof timestamp === 'number') {
    // If it's a small number, it's likely Unix seconds - convert to ms
    date = new Date(timestamp < 10000000000 ? timestamp * 1000 : timestamp);
  } else {
    // Try parsing as date string (ISO format, etc.)
    date = new Date(timestamp);
  }
  
  // Check if date is valid
  return isNaN(date.getTime()) ? null : date;
};

/**
 * Format a timestamp as relative time (e.g., "5 min ago", "2 days ago")
 */
export const formatTimeAgo = (timestamp: string | number | null | undefined): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown';
  
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
  });
};

/**
 * Format a timestamp with more detail (e.g., "5 min ago", "2 hours ago")
 */
export const formatTimestampDetailed = (timestamp: string | number | null | undefined): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown';
  
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
  });
};

/**
 * Get date group label (Today, Yesterday, or formatted date)
 */
export const getDateGroupLabel = (timestamp: string | number | null | undefined): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown Date';
  
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  
  if (date.toDateString() === today.toDateString()) {
    return 'Today';
  } else if (date.toDateString() === yesterday.toDateString()) {
    return 'Yesterday';
  } else {
    return date.toLocaleDateString('en-US', { 
      weekday: 'long', 
      month: 'long', 
      day: 'numeric' 
    });
  }
};

/**
 * Format date for display
 */
export const formatDate = (timestamp: string | number | null | undefined, options?: Intl.DateTimeFormatOptions): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown';
  
  return date.toLocaleDateString('en-US', options || {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
};

/**
 * Format date and time
 */
export const formatDateTime = (
  timestamp: string | number | null | undefined,
  timeFormat: '12h' | '24h' = '12h'
): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown';
  
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: timeFormat === '12h'
  });
};

/**
 * Format time only (e.g., "3:00 PM" or "15:00")
 */
export const formatTime = (
  timestamp: string | number | null | undefined,
  timeFormat: '12h' | '24h' = '12h'
): string => {
  const date = parseTimestamp(timestamp);
  
  if (!date) return 'Unknown';
  
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: timeFormat === '12h'
  });
};

/**
 * Format time from HH:MM string (e.g., "15:00" → "3:00 PM" or "15:00")
 */
export const formatTimeString = (
  time: string | null | undefined,
  timeFormat: '12h' | '24h' = '12h'
): string => {
  if (!time) return 'Unknown';
  
  // Parse HH:MM format
  const match = time.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return time; // Return as-is if not in expected format
  
  const hours = parseInt(match[1], 10);
  const minutes = match[2];
  
  if (timeFormat === '24h') {
    return `${hours.toString().padStart(2, '0')}:${minutes}`;
  }
  
  // Convert to 12-hour format
  const period = hours >= 12 ? 'PM' : 'AM';
  const hour12 = hours % 12 || 12;
  return `${hour12}:${minutes} ${period}`;
};
