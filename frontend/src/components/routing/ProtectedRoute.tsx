import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { getProfileStatus } from '../../utils/profileCompletion';
import { api } from '../../api/client';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiresAuth?: boolean;
  skipProfileCheck?: boolean; // For routes like /complete-setup, /complete-profile
  skipPricingCheck?: boolean; // For pricing setup page
}

// Routes that should skip profile completion checks
const PROFILE_CHECK_EXEMPT_ROUTES = [
  '/onboarding',
  '/complete-setup',
  '/complete-profile',
  '/setup/pricing',
  '/settings',
];

// Routes that should skip pricing checks
const PRICING_CHECK_EXEMPT_ROUTES = [
  '/setup/pricing',
  '/settings',
  '/onboarding',
  '/complete-setup',
  '/complete-profile',
];

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  requiresAuth = true,
  skipProfileCheck = false,
  skipPricingCheck = false,
}) => {
  const { state } = useAuth();
  const location = useLocation();
  const [pricingLoading, setPricingLoading] = useState(false);
  const [hasPricing, setHasPricing] = useState<boolean | null>(null);
  
  // Check pricing status (skip if not authenticated or if check is skipped)
  const shouldCheckPricing = requiresAuth && state.isAuthenticated && !skipPricingCheck;
  useEffect(() => {
    if (!shouldCheckPricing) {
      setPricingLoading(false);
      return;
    }
    let cancelled = false;
    setPricingLoading(true);
    api.resources.list('daycare_pricing', { limit: 1, is_active: true })
      .then((rows) => { if (!cancelled) setHasPricing(rows.length > 0); })
      .catch(() => { if (!cancelled) setHasPricing(null); })
      .finally(() => { if (!cancelled) setPricingLoading(false); });
    return () => { cancelled = true; };
  }, [shouldCheckPricing, state.token]);

  // Not authenticated - redirect to login
  if (requiresAuth && !state.isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Authenticated but accessing login/register - redirect based on profile status
  if (!requiresAuth && state.isAuthenticated) {
    const profileStatus = getProfileStatus(state.user, state.organization);
    if (profileStatus.redirectTo) {
      return <Navigate to={profileStatus.redirectTo} replace />;
    }
    return <Navigate to="/dashboard" replace />;
  }

  // 1. CHECK ORG INFO FIRST - redirect to complete-setup if fields missing
  if (requiresAuth && state.isAuthenticated && !skipProfileCheck) {
    const isExemptRoute = PROFILE_CHECK_EXEMPT_ROUTES.some(route => 
      location.pathname.startsWith(route)
    );
    
    if (!isExemptRoute) {
      const profileStatus = getProfileStatus(state.user, state.organization);
      if (profileStatus.redirectTo) {
        return <Navigate to={profileStatus.redirectTo} replace />;
      }
    }
  }
  
  // Show loading while checking pricing
  if (shouldCheckPricing && pricingLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
      </div>
    );
  }
  
  // 2. THEN check pricing - redirect to pricing setup if not configured
  if (shouldCheckPricing && !pricingLoading) {
    const isPricingExemptRoute = PRICING_CHECK_EXEMPT_ROUTES.some(route => 
      location.pathname.startsWith(route)
    );
    
    if (!isPricingExemptRoute && hasPricing === false) {
      return <Navigate to="/setup/pricing" replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;
