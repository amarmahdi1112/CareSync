// ============================================
// Daycare Pricing Setup Page
// Required step before accessing dashboard
// ============================================

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  CurrencyDollarIcon,
  UserGroupIcon,
  AcademicCapIcon,
  BuildingOfficeIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';
import { api } from '../../api/client';
import { useApiQuery } from '../../api/hooks';

// -------------------- Types --------------------

interface DaycarePricingResponse {
  daycarePricing: {
    id: string;
    rate_type: 'daily' | 'hourly' | 'monthly';
    infant_full_day_rate?: number;
    infant_half_day_rate?: number;
    infant_hourly_rate?: number;
    toddler_full_day_rate?: number;
    toddler_half_day_rate?: number;
    toddler_hourly_rate?: number;
    preschool_full_day_rate?: number;
    preschool_half_day_rate?: number;
    preschool_hourly_rate?: number;
    kinder_full_day_rate?: number;
    kinder_half_day_rate?: number;
    kinder_hourly_rate?: number;
    osc_full_day_rate?: number;
    osc_half_day_rate?: number;
    osc_hourly_rate?: number;
    osc_before_school_rate?: number;
    osc_after_school_rate?: number;
    registration_fee?: number;
    late_pickup_fee_per_minute?: number;
    supplies_fee_monthly?: number;
    infant_parent_portion?: number;
    toddler_parent_portion?: number;
    preschool_parent_portion?: number;
    kinder_parent_portion?: number;
    osc_parent_portion?: number;
  } | null;
}

interface PricingData {
  rate_type: 'daily' | 'hourly' | 'monthly';
  
  // Infant rates
  infant_full_day_rate: string;
  infant_half_day_rate: string;
  infant_hourly_rate: string;
  
  // Toddler rates
  toddler_full_day_rate: string;
  toddler_half_day_rate: string;
  toddler_hourly_rate: string;
  
  // Preschool rates
  preschool_full_day_rate: string;
  preschool_half_day_rate: string;
  preschool_hourly_rate: string;
  
  // Kindergarten rates
  kinder_full_day_rate: string;
  kinder_half_day_rate: string;
  kinder_hourly_rate: string;
  
  // OSC rates
  osc_full_day_rate: string;
  osc_half_day_rate: string;
  osc_hourly_rate: string;
  osc_before_school_rate: string;
  osc_after_school_rate: string;
  
  // Fees
  registration_fee: string;
  late_pickup_fee_per_minute: string;
  supplies_fee_monthly: string;
  
  // Parent portions
  infant_parent_portion: string;
  toddler_parent_portion: string;
  preschool_parent_portion: string;
  kinder_parent_portion: string;
  osc_parent_portion: string;
}

const initialPricing: PricingData = {
  rate_type: 'daily',
  infant_full_day_rate: '',
  infant_half_day_rate: '',
  infant_hourly_rate: '',
  toddler_full_day_rate: '',
  toddler_half_day_rate: '',
  toddler_hourly_rate: '',
  preschool_full_day_rate: '',
  preschool_half_day_rate: '',
  preschool_hourly_rate: '',
  kinder_full_day_rate: '',
  kinder_half_day_rate: '',
  kinder_hourly_rate: '',
  osc_full_day_rate: '',
  osc_half_day_rate: '',
  osc_hourly_rate: '',
  osc_before_school_rate: '',
  osc_after_school_rate: '',
  registration_fee: '',
  late_pickup_fee_per_minute: '',
  supplies_fee_monthly: '',
  infant_parent_portion: '',
  toddler_parent_portion: '',
  preschool_parent_portion: '',
  kinder_parent_portion: '',
  osc_parent_portion: '',
};

// -------------------- Age Group Card --------------------

interface AgeGroupCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  prefix: string;
  values: PricingData;
  onChange: (field: keyof PricingData, value: string) => void;
  showOscExtras?: boolean;
  parentPortionField: keyof PricingData;
}

const AgeGroupCard: React.FC<AgeGroupCardProps> = ({
  title,
  description,
  icon,
  prefix,
  values,
  onChange,
  showOscExtras = false,
  parentPortionField,
}) => {
  const fullDayField = `${prefix}_full_day_rate` as keyof PricingData;
  
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-4">
        <div className="p-3 bg-primary-50 rounded-lg text-primary-600">
          {icon}
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-gray-900">{title}</h3>
          <p className="text-sm text-gray-500 mb-4">{description}</p>
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Full Daycare Payment (Monthly)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={values[fullDayField]}
                  onChange={(e) => onChange(fullDayField, e.target.value)}
                  placeholder="0.00"
                  className="w-full pl-7 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-green-700 mb-1">Parent Pays (Monthly)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-green-500 text-sm">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={values[parentPortionField]}
                  onChange={(e) => onChange(parentPortionField, e.target.value)}
                  placeholder="326.25"
                  className="w-full pl-7 pr-3 py-2 border border-green-200 rounded-lg text-sm focus:ring-2 focus:ring-green-500 focus:border-transparent bg-green-50"
                />
              </div>
            </div>
          </div>
          
          {showOscExtras && (
            <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-gray-100">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Before School</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={values.osc_before_school_rate}
                    onChange={(e) => onChange('osc_before_school_rate', e.target.value)}
                    placeholder="0.00"
                    className="w-full pl-7 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">After School</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={values.osc_after_school_rate}
                    onChange={(e) => onChange('osc_after_school_rate', e.target.value)}
                    placeholder="0.00"
                    className="w-full pl-7 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// -------------------- Main Component --------------------

const PricingSetup: React.FC = () => {
  const navigate = useNavigate();
  const [pricing, setPricing] = useState<PricingData>(initialPricing);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  
  // Load existing pricing
  const { data: pricingRows, loading: loadingExisting } = useApiQuery<Array<NonNullable<DaycarePricingResponse['daycarePricing']>>>('/resources/daycare_pricing', { limit: 1 });
  const existingData: DaycarePricingResponse | undefined = pricingRows
    ? { daycarePricing: pricingRows[0] || null }
    : undefined;
  
  // Load existing data into form
  useEffect(() => {
    if (existingData?.daycarePricing) {
      const p = existingData.daycarePricing;
      setPricing({
        rate_type: p.rate_type || 'daily',
        infant_full_day_rate: p.infant_full_day_rate?.toString() || '',
        infant_half_day_rate: p.infant_half_day_rate?.toString() || '',
        infant_hourly_rate: p.infant_hourly_rate?.toString() || '',
        toddler_full_day_rate: p.toddler_full_day_rate?.toString() || '',
        toddler_half_day_rate: p.toddler_half_day_rate?.toString() || '',
        toddler_hourly_rate: p.toddler_hourly_rate?.toString() || '',
        preschool_full_day_rate: p.preschool_full_day_rate?.toString() || '',
        preschool_half_day_rate: p.preschool_half_day_rate?.toString() || '',
        preschool_hourly_rate: p.preschool_hourly_rate?.toString() || '',
        kinder_full_day_rate: p.kinder_full_day_rate?.toString() || '',
        kinder_half_day_rate: p.kinder_half_day_rate?.toString() || '',
        kinder_hourly_rate: p.kinder_hourly_rate?.toString() || '',
        osc_full_day_rate: p.osc_full_day_rate?.toString() || '',
        osc_half_day_rate: p.osc_half_day_rate?.toString() || '',
        osc_hourly_rate: p.osc_hourly_rate?.toString() || '',
        osc_before_school_rate: p.osc_before_school_rate?.toString() || '',
        osc_after_school_rate: p.osc_after_school_rate?.toString() || '',
        registration_fee: p.registration_fee?.toString() || '',
        late_pickup_fee_per_minute: p.late_pickup_fee_per_minute?.toString() || '',
        supplies_fee_monthly: p.supplies_fee_monthly?.toString() || '',
        infant_parent_portion: p.infant_parent_portion?.toString() || '',
        toddler_parent_portion: p.toddler_parent_portion?.toString() || '',
        preschool_parent_portion: p.preschool_parent_portion?.toString() || '',
        kinder_parent_portion: p.kinder_parent_portion?.toString() || '',
        osc_parent_portion: p.osc_parent_portion?.toString() || '',
      });
    }
  }, [existingData]);
  
  const handleChange = (field: keyof PricingData, value: string) => {
    setPricing(prev => ({ ...prev, [field]: value }));
  };
  
  const handleSubmit = async () => {
    setError(null);
    
    // Check that at least one rate is set
    const hasAnyRate = [
      pricing.infant_full_day_rate,
      pricing.toddler_full_day_rate,
      pricing.preschool_full_day_rate,
      pricing.kinder_full_day_rate,
      pricing.osc_full_day_rate,
    ].some(rate => rate && parseFloat(rate) > 0);
    
    if (!hasAnyRate) {
      setError('Please set at least one daily rate for the age groups you serve.');
      return;
    }
    
    // Convert string values to numbers
    const input = {
      rate_type: pricing.rate_type,
      infant_full_day_rate: pricing.infant_full_day_rate ? parseFloat(pricing.infant_full_day_rate) : null,
      infant_half_day_rate: pricing.infant_half_day_rate ? parseFloat(pricing.infant_half_day_rate) : null,
      infant_hourly_rate: pricing.infant_hourly_rate ? parseFloat(pricing.infant_hourly_rate) : null,
      toddler_full_day_rate: pricing.toddler_full_day_rate ? parseFloat(pricing.toddler_full_day_rate) : null,
      toddler_half_day_rate: pricing.toddler_half_day_rate ? parseFloat(pricing.toddler_half_day_rate) : null,
      toddler_hourly_rate: pricing.toddler_hourly_rate ? parseFloat(pricing.toddler_hourly_rate) : null,
      preschool_full_day_rate: pricing.preschool_full_day_rate ? parseFloat(pricing.preschool_full_day_rate) : null,
      preschool_half_day_rate: pricing.preschool_half_day_rate ? parseFloat(pricing.preschool_half_day_rate) : null,
      preschool_hourly_rate: pricing.preschool_hourly_rate ? parseFloat(pricing.preschool_hourly_rate) : null,
      kinder_full_day_rate: pricing.kinder_full_day_rate ? parseFloat(pricing.kinder_full_day_rate) : null,
      kinder_half_day_rate: pricing.kinder_half_day_rate ? parseFloat(pricing.kinder_half_day_rate) : null,
      kinder_hourly_rate: pricing.kinder_hourly_rate ? parseFloat(pricing.kinder_hourly_rate) : null,
      osc_full_day_rate: pricing.osc_full_day_rate ? parseFloat(pricing.osc_full_day_rate) : null,
      osc_half_day_rate: pricing.osc_half_day_rate ? parseFloat(pricing.osc_half_day_rate) : null,
      osc_hourly_rate: pricing.osc_hourly_rate ? parseFloat(pricing.osc_hourly_rate) : null,
      osc_before_school_rate: pricing.osc_before_school_rate ? parseFloat(pricing.osc_before_school_rate) : null,
      osc_after_school_rate: pricing.osc_after_school_rate ? parseFloat(pricing.osc_after_school_rate) : null,
      registration_fee: pricing.registration_fee ? parseFloat(pricing.registration_fee) : null,
      late_pickup_fee_per_minute: pricing.late_pickup_fee_per_minute ? parseFloat(pricing.late_pickup_fee_per_minute) : null,
      supplies_fee_monthly: pricing.supplies_fee_monthly ? parseFloat(pricing.supplies_fee_monthly) : null,
      infant_parent_portion: pricing.infant_parent_portion ? parseFloat(pricing.infant_parent_portion) : null,
      toddler_parent_portion: pricing.toddler_parent_portion ? parseFloat(pricing.toddler_parent_portion) : null,
      preschool_parent_portion: pricing.preschool_parent_portion ? parseFloat(pricing.preschool_parent_portion) : null,
      kinder_parent_portion: pricing.kinder_parent_portion ? parseFloat(pricing.kinder_parent_portion) : null,
      osc_parent_portion: pricing.osc_parent_portion ? parseFloat(pricing.osc_parent_portion) : null,
    };
    
    try {
      setSaving(true);
      const existing = existingData?.daycarePricing;
      if (existing?.id) {
        await api.resources.update('daycare_pricing', existing.id, input);
      } else {
        await api.resources.create('daycare_pricing', input);
      }
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save pricing');
    } finally {
      setSaving(false);
    }
  };
  
  if (loadingExisting) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 via-white to-blue-50">
      <div className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary-100 rounded-full mb-4">
            <CurrencyDollarIcon className="w-8 h-8 text-primary-600" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Set Up Your Pricing</h1>
          <p className="text-gray-600 max-w-lg mx-auto">
            Configure your rates by age group. This allows automatic invoice calculations 
            for your families. You can always update these later in Settings.
          </p>
        </div>
        
        {/* Info Banner */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-8 flex items-start gap-3">
          <InformationCircleIcon className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-800">
            <p className="font-medium mb-1">Only fill in the age groups you serve</p>
            <p className="text-blue-600">
              Leave fields empty for age groups you don't offer. You can add or modify 
              rates anytime from your settings.
            </p>
          </div>
        </div>
        
        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 mb-8 text-red-700">
            {error}
          </div>
        )}
        
        {/* Age Group Cards */}
        <div className="space-y-4 mb-8">
          <AgeGroupCard
            title="Infants"
            description="0-18 months"
            icon={<UserGroupIcon className="w-6 h-6" />}
            prefix="infant"
            values={pricing}
            onChange={handleChange}
            parentPortionField="infant_parent_portion"
          />
          
          <AgeGroupCard
            title="Toddlers"
            description="18 months - 3 years"
            icon={<UserGroupIcon className="w-6 h-6" />}
            prefix="toddler"
            values={pricing}
            onChange={handleChange}
            parentPortionField="toddler_parent_portion"
          />
          
          <AgeGroupCard
            title="Preschoolers"
            description="3-4 years"
            icon={<AcademicCapIcon className="w-6 h-6" />}
            prefix="preschool"
            values={pricing}
            onChange={handleChange}
            parentPortionField="preschool_parent_portion"
          />
          
          <AgeGroupCard
            title="Kindergarteners"
            description="5-6 years"
            icon={<AcademicCapIcon className="w-6 h-6" />}
            prefix="kinder"
            values={pricing}
            onChange={handleChange}
            parentPortionField="kinder_parent_portion"
          />
          
          <AgeGroupCard
            title="Out of School Care (OSC)"
            description="6+ years / School age"
            icon={<BuildingOfficeIcon className="w-6 h-6" />}
            prefix="osc"
            values={pricing}
            onChange={handleChange}
            showOscExtras
            parentPortionField="osc_parent_portion"
          />
        </div>
        
        {/* Additional Fees */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-8">
          <h3 className="font-semibold text-gray-900 mb-4">Additional Fees (Optional)</h3>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Registration Fee</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={pricing.registration_fee}
                  onChange={(e) => handleChange('registration_fee', e.target.value)}
                  placeholder="0.00"
                  className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Late Pickup (per min)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={pricing.late_pickup_fee_per_minute}
                  onChange={(e) => handleChange('late_pickup_fee_per_minute', e.target.value)}
                  placeholder="0.00"
                  className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Monthly Supplies</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={pricing.supplies_fee_monthly}
                  onChange={(e) => handleChange('supplies_fee_monthly', e.target.value)}
                  placeholder="0.00"
                  className="w-full pl-8 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
          </div>
        </div>
        
        {/* Submit */}
        <div className="flex justify-end">
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="inline-flex items-center gap-2 px-8 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-lg shadow-primary-600/20"
          >
            {saving ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Saving...
              </>
            ) : (
              <>
                <CheckCircleIcon className="w-5 h-5" />
                Save & Continue
                <ArrowRightIcon className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PricingSetup;
