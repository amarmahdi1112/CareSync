import React from 'react';
import { Link } from 'react-router-dom';
import {
  HeartIcon,
  LightBulbIcon,
  ShieldCheckIcon,
  UserGroupIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

const About: React.FC = () => {
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
              <Link to="/about" className="text-primary-600 font-medium">About</Link>
              <Link to="/pricing" className="text-gray-600 hover:text-gray-900 transition-colors">Pricing</Link>
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
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl font-bold text-gray-900 mb-6">
            Built for Childcare, 
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-600 to-purple-600"> By Childcare </span>
            Professionals
          </h1>
          <p className="text-xl text-gray-600 leading-relaxed">
            We understand the challenges of running a childcare center. That's why we built CareSync—to give 
            you back the time to focus on what matters most: the children.
          </p>
        </div>
      </section>

      {/* Mission */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div>
              <h2 className="text-3xl font-bold text-gray-900 mb-6">Our Mission</h2>
              <p className="text-lg text-gray-600 mb-6 leading-relaxed">
                We believe every childcare provider deserves access to modern, intuitive software that simplifies 
                their daily operations. Our mission is to empower daycares and out-of-school care programs with 
                tools that reduce administrative burden and enhance the care they provide.
              </p>
              <p className="text-lg text-gray-600 leading-relaxed">
                From family registration to invoicing, attendance tracking to compliance management—we've 
                built a comprehensive solution that grows with your organization.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-6">
              {[
                { icon: HeartIcon, title: 'Child-Focused', desc: 'Every feature designed with children\'s wellbeing in mind', color: 'bg-red-500' },
                { icon: LightBulbIcon, title: 'Innovative', desc: 'Constantly improving based on your feedback', color: 'bg-amber-500' },
                { icon: ShieldCheckIcon, title: 'Secure', desc: 'Enterprise-grade security for your data', color: 'bg-green-500' },
                { icon: UserGroupIcon, title: 'Supportive', desc: '24/7 support from our dedicated team', color: 'bg-blue-500' },
              ].map((item, i) => (
                <div key={i} className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                  <div className={`w-12 h-12 ${item.color} rounded-xl flex items-center justify-center mb-4`}>
                    <item.icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="font-semibold text-gray-900 mb-2">{item.title}</h3>
                  <p className="text-sm text-gray-600">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-4 gap-8 text-center">
            {[
              { value: '500+', label: 'Centers Using CareSync' },
              { value: '25,000+', label: 'Children Managed' },
              { value: '99.9%', label: 'Uptime Guaranteed' },
              { value: '4.9/5', label: 'Customer Rating' },
            ].map((stat, i) => (
              <div key={i}>
                <div className="text-4xl font-bold text-primary-600 mb-2">{stat.value}</div>
                <div className="text-gray-600">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Values */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-gray-900 mb-12 text-center">Our Core Values</h2>
          <div className="space-y-8">
            {[
              {
                title: 'Simplicity First',
                desc: 'We believe powerful software doesn\'t have to be complicated. Every feature is designed to be intuitive and easy to use, even for those who aren\'t tech-savvy.',
              },
              {
                title: 'Privacy & Security',
                desc: 'Children\'s data requires the highest level of protection. We use industry-leading security practices and are fully compliant with privacy regulations.',
              },
              {
                title: 'Continuous Improvement',
                desc: 'We listen to our customers and continuously improve our platform. Your feedback directly shapes our product roadmap.',
              },
              {
                title: 'Accessible to All',
                desc: 'Quality childcare management software should be accessible to centers of all sizes. Our pricing reflects this commitment to accessibility.',
              },
            ].map((value, i) => (
              <div key={i} className="flex gap-6">
                <div className="flex-shrink-0 w-8 h-8 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center font-bold">
                  {i + 1}
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-gray-900 mb-2">{value.title}</h3>
                  <p className="text-gray-600 leading-relaxed">{value.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-6">Join Our Growing Community</h2>
          <p className="text-xl text-gray-600 mb-8">
            Start your free trial today and see why hundreds of childcare providers trust CareSync.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all hover:shadow-xl hover:shadow-primary-500/25"
          >
            Get Started Free
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

export default About;
