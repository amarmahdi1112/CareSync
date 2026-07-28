import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CheckIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

const Pricing: React.FC = () => {
  const [annual, setAnnual] = useState(true);

  const plans = [
    {
      name: 'Starter',
      desc: 'Perfect for small daycares just getting started',
      monthlyPrice: 49,
      annualPrice: 39,
      capacity: 'Up to 25 children',
      features: [
        'Family registration & management',
        'Basic invoicing',
        'Attendance tracking',
        'Email support',
        '1 admin user',
      ],
      popular: false,
    },
    {
      name: 'Professional',
      desc: 'For growing centers that need more power',
      monthlyPrice: 99,
      annualPrice: 79,
      capacity: 'Up to 75 children',
      features: [
        'Everything in Starter',
        'Advanced invoicing & subsidies',
        'Custom reports & analytics',
        'Parent portal access',
        'Priority email & chat support',
        '5 admin users',
        'Document management',
      ],
      popular: true,
    },
    {
      name: 'Enterprise',
      desc: 'For large organizations & multi-location centers',
      monthlyPrice: 199,
      annualPrice: 159,
      capacity: 'Unlimited children',
      features: [
        'Everything in Professional',
        'Multi-location support',
        'Custom integrations',
        'Dedicated account manager',
        'Phone support',
        'Unlimited admin users',
        'Advanced compliance tools',
        'Custom branding',
      ],
      popular: false,
    },
  ];

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-2">
              <img src={logoSvg} alt="CareSync" className="h-10 w-auto" />
            </Link>
            <div className="hidden md:flex items-center gap-8">
              <Link to="/about" className="text-gray-600 hover:text-gray-900 transition-colors">About</Link>
              <Link to="/pricing" className="text-primary-600 font-medium">Pricing</Link>
              <Link to="/contact" className="text-gray-600 hover:text-gray-900 transition-colors">Contact</Link>
            </div>
            <div className="flex items-center gap-4">
              <Link to="/login" className="text-gray-600 hover:text-gray-900 font-medium transition-colors">
                Sign In
              </Link>
              <Link
                to="/register"
                className="bg-primary-600 hover:bg-primary-700 text-white px-5 py-2.5 rounded-xl font-medium transition-all hover:shadow-lg hover:shadow-primary-500/25"
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl font-bold text-gray-900 mb-6">
            Simple, Transparent Pricing
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Choose the plan that fits your center. All plans include a 14-day free trial.
          </p>
          
          {/* Billing Toggle */}
          <div className="inline-flex items-center gap-4 bg-gray-100 p-1 rounded-xl">
            <button
              onClick={() => setAnnual(false)}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                !annual ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600'
              }`}
            >
              Monthly
            </button>
            <button
              onClick={() => setAnnual(true)}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                annual ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600'
              }`}
            >
              Annual
              <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                Save 20%
              </span>
            </button>
          </div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8">
            {plans.map((plan, i) => (
              <div
                key={i}
                className={`relative bg-white rounded-2xl p-8 border-2 transition-all ${
                  plan.popular
                    ? 'border-primary-500 shadow-xl shadow-primary-500/10 scale-105'
                    : 'border-gray-100 hover:border-gray-200 hover:shadow-lg'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-gradient-to-r from-primary-600 to-purple-600 text-white text-sm font-medium px-4 py-1 rounded-full">
                    Most Popular
                  </div>
                )}
                <div className="text-center mb-8">
                  <h3 className="text-2xl font-bold text-gray-900 mb-2">{plan.name}</h3>
                  <p className="text-gray-600 text-sm mb-4">{plan.desc}</p>
                  <div className="flex items-baseline justify-center gap-1">
                    <span className="text-5xl font-bold text-gray-900">
                      ${annual ? plan.annualPrice : plan.monthlyPrice}
                    </span>
                    <span className="text-gray-500">/month</span>
                  </div>
                  <p className="text-sm text-gray-500 mt-2">{plan.capacity}</p>
                </div>
                <ul className="space-y-4 mb-8">
                  {plan.features.map((feature, j) => (
                    <li key={j} className="flex items-start gap-3">
                      <CheckIcon className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-600">{feature}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  to="/register"
                  className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold transition-all ${
                    plan.popular
                      ? 'bg-primary-600 hover:bg-primary-700 text-white hover:shadow-lg hover:shadow-primary-500/25'
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
                  }`}
                >
                  Start Free Trial
                  <ArrowRightIcon className="w-4 h-4" />
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 mb-12 text-center">Frequently Asked Questions</h2>
          <div className="space-y-6">
            {[
              {
                q: 'Can I change plans later?',
                a: 'Absolutely! You can upgrade or downgrade your plan at any time. Changes take effect at the start of your next billing cycle.',
              },
              {
                q: 'What happens after my free trial?',
                a: 'After your 14-day trial, you\'ll be prompted to choose a plan. If you don\'t select a plan, your account will be paused until you subscribe.',
              },
              {
                q: 'Is there a setup fee?',
                a: 'No setup fees, ever. You only pay the monthly or annual subscription fee for your chosen plan.',
              },
              {
                q: 'Can I cancel anytime?',
                a: 'Yes, you can cancel your subscription at any time. Your access will continue until the end of your current billing period.',
              },
              {
                q: 'Do you offer discounts for non-profits?',
                a: 'Yes! We offer a 25% discount for registered non-profit organizations. Contact us to learn more.',
              },
            ].map((faq, i) => (
              <div key={i} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
                <h3 className="font-semibold text-gray-900 mb-2">{faq.q}</h3>
                <p className="text-gray-600">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-6">Ready to Get Started?</h2>
          <p className="text-xl text-gray-600 mb-8">
            Join hundreds of childcare providers using CareSync. No credit card required.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all hover:shadow-xl hover:shadow-primary-500/25"
          >
            Start Your Free Trial
            <ArrowRightIcon className="w-5 h-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <img src={logoSvg} alt="CareSync" className="h-8 w-auto" />
          </div>
          <p className="text-gray-500 text-sm">
            © {new Date().getFullYear()} CareSync. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Pricing;
