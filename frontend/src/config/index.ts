/**
 * Frontend Configuration
 * Automatically switches between development and production settings
 */

// Detect environment
const isDevelopment = import.meta.env.DEV || import.meta.env.MODE === 'development';
const isProduction = import.meta.env.PROD || import.meta.env.MODE === 'production';

const LOCAL_API_URL = 'http://127.0.0.1:3001/api/v1';

/**
 * Application configuration
 */
export const config = {
  // Environment
  isDevelopment,
  isProduction,
  
  // API URLs - can be overridden by env variables
  apiUrl: import.meta.env.VITE_API_URL || LOCAL_API_URL,
  // Temporary compatibility URL while the remaining screens move to REST.
  graphqlUrl: import.meta.env.VITE_GRAPHQL_URL || 'http://127.0.0.1:3001/graphql',
  
  // Helper to build full URLs for uploaded assets
  getUploadUrl: (path: string): string => {
    if (!path) return '';
    // If already a full URL, return as-is
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return path;
    }
    const apiUrl = import.meta.env.VITE_API_URL || LOCAL_API_URL;
    const baseUrl = apiUrl.replace(/\/api\/v1\/?$/, '');
    return `${baseUrl}${path}`;
  },
};

export default config;
