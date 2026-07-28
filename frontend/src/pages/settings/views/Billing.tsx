// ============================================
// Billing Settings View (Refactored)
// ============================================

import React, { useState } from 'react';
import {
  CreditCardIcon,
  CheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { useAuth } from '../../../context/AuthContext';
import { useNotifications } from '../../../components/ui/NotificationContainer';

// Types
import type { Plan } from '../types';

// Components
import {
  SettingsPageLayout,
  SettingsSection,
  SettingsTabs,
} from '../components';

// -------------------- Plan Data --------------------

const plans: Plan[] = [
  {
    id: 'starter',
    name: 'Starter',
    price: 0,
    description: 'Perfect for getting started',
    features: ['Up to 10 children', '1 staff account', 'Basic attendance', 'Email support'],
    maxChildren: 10,
    maxStaff: 1,
  },
  {
    id: 'professional',
    name: 'Professional',
    price: 49,
    description: 'For growing childcare centers',
    features: ['Up to 50 children', '5 staff accounts', 'Full attendance', 'Invoicing', 'Reports', 'Priority support'],
    popular: true,
    maxChildren: 50,
    maxStaff: 5,
  },
  {
    id: 'business',
    name: 'Business',
    price: 99,
    description: 'For established centers',
    features: ['Up to 150 children', '15 staff accounts', 'All features', 'Custom reports', 'API access', 'Phone support'],
    maxChildren: 150,
    maxStaff: 15,
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 199,
    description: 'For large organizations',
    features: ['Unlimited children', 'Unlimited staff', 'All features', 'Dedicated support', 'Custom integrations', 'SLA'],
  },
];

type TabType = 'plans' | 'payment' | 'invoices';

const tabs = [
  { id: 'plans' as TabType, name: 'Plans', icon: SparklesIcon },
  { id: 'payment' as TabType, name: 'Payment Method', icon: CreditCardIcon },
];

const Billing: React.FC = () => {
  const { state } = useAuth();
  const organization = state.organization;
  const { addNotification } = useNotifications();
  const [activeTab, setActiveTab] = useState<TabType>('plans');
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');

  const currentPlanId = organization?.subscription_plan || 'starter';

  const handleUpgrade = () => {
    addNotification({
      type: 'info',
      title: 'Coming Soon',
      message: 'Payment processing will be available soon. Contact us for enterprise plans.',
    });
  };

  const getPrice = (plan: Plan) => {
    if (billingCycle === 'yearly') {
      return Math.floor(plan.price * 10); // 2 months free
    }
    return plan.price;
  };

  return (
    <SettingsPageLayout
      title="Billing & Subscription"
      description="Manage your subscription plan and payment methods."
    >
      <SettingsTabs tabs={tabs} activeTab={activeTab} onTabChange={(id) => setActiveTab(id as TabType)} />

      {activeTab === 'plans' && (
        <div className="space-y-6">
          {/* Billing Cycle Toggle */}
          <div className="flex items-center justify-center gap-4 p-4 bg-gray-50 rounded-xl">
            <span className={`text-sm font-medium ${billingCycle === 'monthly' ? 'text-gray-900' : 'text-gray-500'}`}>
              Monthly
            </span>
            <button
              onClick={() => setBillingCycle(billingCycle === 'monthly' ? 'yearly' : 'monthly')}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                billingCycle === 'yearly' ? 'bg-primary-600' : 'bg-gray-300'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  billingCycle === 'yearly' ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
            <span className={`text-sm font-medium ${billingCycle === 'yearly' ? 'text-gray-900' : 'text-gray-500'}`}>
              Yearly
              <span className="ml-1 text-green-600">(Save 17%)</span>
            </span>
          </div>

          {/* Plans Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {plans.map((plan) => {
              const isCurrent = plan.id === currentPlanId;
              const price = getPrice(plan);

              return (
                <PlanCard
                  key={plan.id}
                  plan={plan}
                  price={price}
                  billingCycle={billingCycle}
                  isCurrent={isCurrent}
                  currentPlanId={currentPlanId}
                  onUpgrade={handleUpgrade}
                />
              );
            })}
          </div>

          {/* Enterprise CTA */}
          <div className="bg-gradient-to-r from-primary-600 to-primary-700 rounded-xl p-6 text-white">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold">Need a custom solution?</h3>
                <p className="mt-1 text-primary-100">
                  Contact us for custom pricing, dedicated support, and tailored features.
                </p>
              </div>
              <button className="px-6 py-2 bg-white text-primary-700 rounded-lg font-medium hover:bg-primary-50">
                Contact Sales
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'payment' && (
        <SettingsSection title="Payment Method" icon={CreditCardIcon}>
          <div className="text-center py-12">
            <CreditCardIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No payment method on file</p>
            <p className="text-sm text-gray-400 mt-1">Add a payment method to upgrade your plan</p>
            <button
              onClick={handleUpgrade}
              className="mt-4 btn btn-primary"
            >
              Add Payment Method
            </button>
          </div>
        </SettingsSection>
      )}
    </SettingsPageLayout>
  );
};

// -------------------- Plan Card Component --------------------

interface PlanCardProps {
  plan: Plan;
  price: number;
  billingCycle: 'monthly' | 'yearly';
  isCurrent: boolean;
  currentPlanId: string;
  onUpgrade: () => void;
}

const PlanCard: React.FC<PlanCardProps> = ({
  plan,
  price,
  billingCycle,
  isCurrent,
  currentPlanId,
  onUpgrade,
}) => {
  const plans_order = ['starter', 'professional', 'business', 'enterprise'];
  const isUpgrade = plans_order.indexOf(plan.id) > plans_order.indexOf(currentPlanId);

  return (
    <div
      className={`relative bg-white rounded-xl border-2 p-5 transition-all ${
        isCurrent
          ? 'border-primary-500 shadow-lg'
          : plan.popular
          ? 'border-primary-200'
          : 'border-gray-200'
      }`}
    >
      {plan.popular && !isCurrent && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-primary-600 text-white text-xs font-medium rounded-full">
          Most Popular
        </span>
      )}
      {isCurrent && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-green-600 text-white text-xs font-medium rounded-full">
          Current Plan
        </span>
      )}

      <div className="text-center mb-4 pt-2">
        <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
        <p className="text-sm text-gray-500 mt-1">{plan.description}</p>
      </div>

      <div className="text-center mb-6">
        <span className="text-3xl font-bold text-gray-900">${price}</span>
        <span className="text-gray-500">/{billingCycle === 'yearly' ? 'year' : 'month'}</span>
      </div>

      <ul className="space-y-2 mb-6">
        {plan.features.map((feature, idx) => (
          <li key={idx} className="flex items-center gap-2 text-sm text-gray-600">
            <CheckIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
            {feature}
          </li>
        ))}
      </ul>

      {isCurrent ? (
        <button disabled className="w-full py-2 px-4 rounded-lg bg-gray-100 text-gray-500 font-medium cursor-not-allowed">
          Current Plan
        </button>
      ) : (
        <button
          onClick={onUpgrade}
          className={`w-full py-2 px-4 rounded-lg font-medium transition-colors ${
            plan.popular
              ? 'bg-primary-600 text-white hover:bg-primary-700'
              : 'bg-gray-100 text-gray-900 hover:bg-gray-200'
          }`}
        >
          {isUpgrade ? 'Upgrade' : 'Downgrade'}
        </button>
      )}
    </div>
  );
};

export default Billing;
