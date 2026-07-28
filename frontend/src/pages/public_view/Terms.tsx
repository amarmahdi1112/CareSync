import React from 'react';
import { Link } from 'react-router-dom';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

const Terms: React.FC = () => {
  const lastUpdated = 'November 27, 2024';

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-2">
              <img src={logoSvg} alt="CareSync" className="h-10 w-auto" />
            </Link>
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

      {/* Content */}
      <div className="pt-24 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-4xl font-bold text-gray-900 mb-4">Terms of Service</h1>
            <p className="text-gray-500">Last updated: {lastUpdated}</p>
          </div>

          <div className="prose prose-lg max-w-none">
            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Agreement to Terms</h2>
              <p className="text-gray-600 mb-4">
                By accessing or using CareSync ("the Service"), you agree to be bound by these Terms of Service 
                ("Terms"). If you disagree with any part of the terms, you may not access the Service.
              </p>
              <p className="text-gray-600">
                These Terms apply to all visitors, users, and others who access or use the Service, including 
                childcare providers, administrators, and staff members.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Description of Service</h2>
              <p className="text-gray-600 mb-4">
                CareSync is a childcare management platform that provides tools for:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Family and child registration management</li>
                <li>Attendance tracking and reporting</li>
                <li>Invoicing and payment processing</li>
                <li>Communication with families</li>
                <li>Compliance and documentation management</li>
                <li>Staff scheduling and management</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. User Accounts</h2>
              <p className="text-gray-600 mb-4">
                When you create an account with us, you must provide accurate, complete, and current information. 
                Failure to do so constitutes a breach of the Terms, which may result in immediate termination of 
                your account.
              </p>
              <p className="text-gray-600 mb-4">
                You are responsible for safeguarding the password that you use to access the Service and for any 
                activities or actions under your password.
              </p>
              <p className="text-gray-600">
                You agree not to disclose your password to any third party. You must notify us immediately upon 
                becoming aware of any breach of security or unauthorized use of your account.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Subscription and Payment</h2>
              <p className="text-gray-600 mb-4">
                Some parts of the Service are billed on a subscription basis ("Subscription(s)"). You will be 
                billed in advance on a recurring and periodic basis ("Billing Cycle"). Billing cycles are set 
                either on a monthly or annual basis.
              </p>
              <p className="text-gray-600 mb-4">
                A valid payment method is required to process the payment for your Subscription. You shall provide 
                accurate and complete billing information.
              </p>
              <p className="text-gray-600">
                Should automatic billing fail, we will issue an electronic invoice requiring manual payment within 
                a specified deadline.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Free Trial</h2>
              <p className="text-gray-600 mb-4">
                CareSync may offer a free trial for a limited period of time ("Free Trial"). You may be required 
                to enter your billing information in order to sign up for the Free Trial.
              </p>
              <p className="text-gray-600">
                If you do not cancel before the Free Trial ends, you will automatically be charged the applicable 
                subscription fee for the plan you selected.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Data Protection and Privacy</h2>
              <p className="text-gray-600 mb-4">
                We are committed to protecting the privacy of children and families. Our collection and use of 
                personal information is governed by our <Link to="/privacy" className="text-primary-600 hover:underline">Privacy Policy</Link>.
              </p>
              <p className="text-gray-600 mb-4">
                You acknowledge that you are responsible for ensuring that you have obtained all necessary consents 
                from families and guardians before entering their personal information into the Service.
              </p>
              <p className="text-gray-600">
                We comply with applicable data protection laws, including PIPEDA (Personal Information Protection 
                and Electronic Documents Act) in Canada.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Acceptable Use</h2>
              <p className="text-gray-600 mb-4">You agree not to use the Service:</p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>For any unlawful purpose or in violation of any applicable laws</li>
                <li>To transmit harmful code, viruses, or malware</li>
                <li>To infringe upon the rights of others</li>
                <li>To harass, abuse, or harm another person</li>
                <li>To impersonate or misrepresent your affiliation with any person or entity</li>
                <li>To collect or store personal data about other users without their consent</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Intellectual Property</h2>
              <p className="text-gray-600 mb-4">
                The Service and its original content (excluding content provided by users), features, and 
                functionality are and will remain the exclusive property of CareSync and its licensors.
              </p>
              <p className="text-gray-600">
                Our trademarks and trade dress may not be used in connection with any product or service without 
                the prior written consent of CareSync.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Termination</h2>
              <p className="text-gray-600 mb-4">
                We may terminate or suspend your account immediately, without prior notice or liability, for any 
                reason whatsoever, including without limitation if you breach the Terms.
              </p>
              <p className="text-gray-600 mb-4">
                Upon termination, your right to use the Service will immediately cease. If you wish to terminate 
                your account, you may simply discontinue using the Service or contact us to close your account.
              </p>
              <p className="text-gray-600">
                You may export your data before termination. After account closure, your data will be retained 
                for a period of 30 days before permanent deletion.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Limitation of Liability</h2>
              <p className="text-gray-600 mb-4">
                In no event shall CareSync, nor its directors, employees, partners, agents, suppliers, or 
                affiliates, be liable for any indirect, incidental, special, consequential, or punitive damages, 
                including without limitation, loss of profits, data, use, goodwill, or other intangible losses.
              </p>
              <p className="text-gray-600">
                Our total liability to you for all claims arising from or related to the Service shall not exceed 
                the amount paid by you to CareSync during the twelve (12) months prior to the claim.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">11. Disclaimer</h2>
              <p className="text-gray-600 mb-4">
                Your use of the Service is at your sole risk. The Service is provided on an "AS IS" and 
                "AS AVAILABLE" basis. The Service is provided without warranties of any kind, whether express 
                or implied.
              </p>
              <p className="text-gray-600">
                CareSync does not warrant that the Service will be uninterrupted, timely, secure, or error-free, 
                or that defects will be corrected.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">12. Governing Law</h2>
              <p className="text-gray-600">
                These Terms shall be governed and construed in accordance with the laws of the Province of Alberta, 
                Canada, without regard to its conflict of law provisions. Any disputes arising from these Terms 
                shall be resolved in the courts of Alberta, Canada.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">13. Changes to Terms</h2>
              <p className="text-gray-600 mb-4">
                We reserve the right to modify or replace these Terms at any time. If a revision is material, we 
                will try to provide at least 30 days' notice prior to any new terms taking effect.
              </p>
              <p className="text-gray-600">
                By continuing to access or use our Service after those revisions become effective, you agree to 
                be bound by the revised terms.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">14. Contact Us</h2>
              <p className="text-gray-600 mb-4">
                If you have any questions about these Terms, please contact us:
              </p>
              <ul className="text-gray-600 space-y-2">
                <li><strong>Email:</strong> legal@caresync.com</li>
                <li><strong>Address:</strong> Edmonton, Alberta, Canada</li>
                <li><strong>Website:</strong> <Link to="/contact" className="text-primary-600 hover:underline">Contact Page</Link></li>
              </ul>
            </section>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <img src={logoSvg} alt="CareSync" className="h-8 w-auto" />
          </div>
          <div className="flex justify-center gap-6 mb-4 text-sm">
            <Link to="/terms" className="text-white">Terms of Service</Link>
            <Link to="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
            <Link to="/contact" className="hover:text-white transition-colors">Contact</Link>
          </div>
          <p className="text-gray-500 text-sm">
            © {new Date().getFullYear()} CareSync. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Terms;
