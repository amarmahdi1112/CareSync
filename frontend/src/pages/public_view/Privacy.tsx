import React from 'react';
import { Link } from 'react-router-dom';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

const Privacy: React.FC = () => {
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
            <h1 className="text-4xl font-bold text-gray-900 mb-4">Privacy Policy</h1>
            <p className="text-gray-500">Last updated: {lastUpdated}</p>
          </div>

          <div className="prose prose-lg max-w-none">
            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">1. Introduction</h2>
              <p className="text-gray-600 mb-4">
                CareSync ("we," "our," or "us") is committed to protecting the privacy of children, families, 
                and childcare providers who use our services. This Privacy Policy explains how we collect, use, 
                disclose, and safeguard your information when you use our childcare management platform.
              </p>
              <p className="text-gray-600">
                We understand the sensitive nature of the information you entrust to us, particularly regarding 
                children. We take our responsibility to protect this information seriously.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">2. Information We Collect</h2>
              
              <h3 className="text-xl font-medium text-gray-800 mt-6 mb-3">2.1 Organization Information</h3>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Business name, address, and contact information</li>
                <li>License and accreditation details</li>
                <li>Operating hours and capacity information</li>
                <li>Bank and payment information for billing</li>
                <li>Staff information (names, roles, certifications)</li>
              </ul>

              <h3 className="text-xl font-medium text-gray-800 mt-6 mb-3">2.2 Family and Guardian Information</h3>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Names, addresses, and contact information</li>
                <li>Emergency contact details</li>
                <li>Billing and payment information</li>
                <li>Authorized pickup persons</li>
              </ul>

              <h3 className="text-xl font-medium text-gray-800 mt-6 mb-3">2.3 Child Information</h3>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Name, date of birth, and gender</li>
                <li>Medical information (allergies, conditions, medications)</li>
                <li>Dietary restrictions and preferences</li>
                <li>Attendance records</li>
                <li>Emergency contacts</li>
                <li>Photographs (with parental consent)</li>
              </ul>

              <h3 className="text-xl font-medium text-gray-800 mt-6 mb-3">2.4 Technical Information</h3>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>IP addresses and device identifiers</li>
                <li>Browser type and operating system</li>
                <li>Usage patterns and feature interactions</li>
                <li>Login timestamps and session data</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">3. How We Use Your Information</h2>
              <p className="text-gray-600 mb-4">We use the information we collect to:</p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Provide and maintain our childcare management services</li>
                <li>Process registrations, attendance, and billing</li>
                <li>Communicate with families and staff</li>
                <li>Generate reports required for licensing and compliance</li>
                <li>Improve and personalize your experience</li>
                <li>Send administrative notifications and updates</li>
                <li>Respond to inquiries and provide support</li>
                <li>Ensure the safety and security of children</li>
                <li>Comply with legal obligations</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">4. Information Sharing</h2>
              <p className="text-gray-600 mb-4">
                We do not sell, trade, or rent personal information. We may share information in the 
                following circumstances:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li><strong>With your consent:</strong> When you authorize sharing with third parties</li>
                <li><strong>Service providers:</strong> With trusted partners who assist in operating our platform 
                    (hosting, payment processing, email services)</li>
                <li><strong>Legal compliance:</strong> When required by law, regulation, or legal process</li>
                <li><strong>Safety:</strong> To protect the rights, property, or safety of children, families, 
                    or others</li>
                <li><strong>Government agencies:</strong> When required for licensing, funding, or regulatory purposes</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">5. Data Security</h2>
              <p className="text-gray-600 mb-4">
                We implement appropriate technical and organizational measures to protect personal information:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Encryption of data in transit and at rest</li>
                <li>Secure authentication and access controls</li>
                <li>Regular security assessments and updates</li>
                <li>Employee training on data protection</li>
                <li>Incident response procedures</li>
                <li>Regular data backups</li>
              </ul>
              <p className="text-gray-600 mt-4">
                While we strive to use commercially acceptable means to protect your information, no method of 
                transmission or storage is 100% secure.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">6. Data Retention</h2>
              <p className="text-gray-600 mb-4">
                We retain personal information for as long as necessary to provide our services and comply with 
                legal obligations:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li><strong>Active accounts:</strong> Data is retained while your account is active</li>
                <li><strong>Closed accounts:</strong> Data is retained for 7 years after account closure to 
                    comply with regulatory requirements</li>
                <li><strong>Child records:</strong> Retained according to provincial childcare regulations 
                    (typically 3-7 years after the child leaves the program)</li>
                <li><strong>Financial records:</strong> Retained for 7 years for tax and audit purposes</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">7. Your Rights</h2>
              <p className="text-gray-600 mb-4">You have the right to:</p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li><strong>Access:</strong> Request a copy of the personal information we hold about you</li>
                <li><strong>Correction:</strong> Request correction of inaccurate or incomplete information</li>
                <li><strong>Deletion:</strong> Request deletion of your personal information, subject to legal 
                    retention requirements</li>
                <li><strong>Data portability:</strong> Request your data in a structured, machine-readable format</li>
                <li><strong>Withdraw consent:</strong> Withdraw previously given consent for data processing</li>
                <li><strong>Complaint:</strong> File a complaint with the relevant privacy authority</li>
              </ul>
              <p className="text-gray-600 mt-4">
                To exercise these rights, please contact us at privacy@caresync.com.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">8. Children's Privacy</h2>
              <p className="text-gray-600 mb-4">
                We are committed to protecting children's privacy. We collect information about children only 
                as necessary to provide childcare management services and only with the consent of parents or 
                guardians.
              </p>
              <p className="text-gray-600 mb-4">
                Parents and guardians have the right to:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Review their child's information</li>
                <li>Request correction or deletion of their child's information</li>
                <li>Withdraw consent for the collection of their child's information</li>
                <li>Opt out of photograph sharing</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">9. Cookies and Tracking</h2>
              <p className="text-gray-600 mb-4">
                We use cookies and similar technologies to:
              </p>
              <ul className="list-disc pl-6 text-gray-600 space-y-2">
                <li>Keep you signed in</li>
                <li>Remember your preferences</li>
                <li>Understand how you use our platform</li>
                <li>Improve our services</li>
              </ul>
              <p className="text-gray-600 mt-4">
                You can control cookies through your browser settings. Disabling cookies may affect some 
                features of the Service.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">10. Third-Party Services</h2>
              <p className="text-gray-600 mb-4">
                Our Service may contain links to third-party websites or integrate with third-party services. 
                We are not responsible for the privacy practices of these third parties. We encourage you to 
                review their privacy policies.
              </p>
              <p className="text-gray-600">
                Third-party services we may use include payment processors, email providers, and cloud hosting 
                services. These providers are contractually obligated to protect your information.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">11. International Data Transfers</h2>
              <p className="text-gray-600">
                Your information may be transferred to and maintained on servers located outside of your 
                province or country. By using our Service, you consent to this transfer. We ensure that any 
                international transfers comply with applicable data protection laws.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">12. Changes to This Policy</h2>
              <p className="text-gray-600 mb-4">
                We may update this Privacy Policy from time to time. We will notify you of any changes by 
                posting the new Privacy Policy on this page and updating the "Last updated" date.
              </p>
              <p className="text-gray-600">
                For significant changes, we will provide additional notice, such as an email notification or 
                a prominent notice within the Service.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="text-2xl font-semibold text-gray-900 mb-4">13. Contact Us</h2>
              <p className="text-gray-600 mb-4">
                If you have questions about this Privacy Policy or our privacy practices, please contact us:
              </p>
              <ul className="text-gray-600 space-y-2">
                <li><strong>Privacy Officer Email:</strong> privacy@caresync.com</li>
                <li><strong>General Email:</strong> support@caresync.com</li>
                <li><strong>Address:</strong> Edmonton, Alberta, Canada</li>
                <li><strong>Website:</strong> <Link to="/contact" className="text-primary-600 hover:underline">Contact Page</Link></li>
              </ul>
            </section>

            <section className="mb-8 p-6 bg-gray-50 rounded-xl">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Provincial Privacy Offices</h2>
              <p className="text-gray-600 mb-4">
                If you are not satisfied with our response to a privacy concern, you may contact:
              </p>
              <ul className="text-gray-600 space-y-2">
                <li><strong>Alberta:</strong> Office of the Information and Privacy Commissioner of Alberta</li>
                <li><strong>Federal:</strong> Office of the Privacy Commissioner of Canada</li>
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
            <Link to="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
            <Link to="/privacy" className="text-white">Privacy Policy</Link>
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

export default Privacy;
