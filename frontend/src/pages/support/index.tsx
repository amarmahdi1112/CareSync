import React, { useState } from 'react';
import {
  QuestionMarkCircleIcon,
  ChatBubbleLeftRightIcon,
  EnvelopeIcon,
  BookOpenIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  MagnifyingGlassIcon,
  PaperAirplaneIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import { useNotifications } from '../../components/ui/NotificationContainer';

interface FAQItem {
  id: string;
  question: string;
  answer: string;
  category: string;
}

const faqItems: FAQItem[] = [
  {
    id: '1',
    question: 'How do I invite staff members to my organization?',
    answer: 'Go to Settings > User Management and click "Invite User". Enter their email, name, and select a role. They will receive an email invitation to join your organization.',
    category: 'Getting Started'
  },
  {
    id: '2',
    question: 'How do I upload my organization logo?',
    answer: 'Navigate to Settings > Organization Settings. In the Profile tab, you\'ll find the logo upload section. Click "Upload" and select an image file (JPG, PNG, GIF, WebP, or SVG) under 5MB.',
    category: 'Getting Started'
  },
  {
    id: '3',
    question: 'How do I register a new family?',
    answer: 'Go to Families in the sidebar and click "Add Family". Follow the step-by-step wizard to enter guardian information, children details, emergency contacts, and consent forms.',
    category: 'Families'
  },
  {
    id: '4',
    question: 'Can I import families from a CSV file?',
    answer: 'Yes! Go to Files > Data Upload and use the CSV Import feature. The system will guide you through mapping columns and handling potential duplicate detection.',
    category: 'Families'
  },
  {
    id: '5',
    question: 'How do I create and send invoices?',
    answer: 'Navigate to Invoicing and click "Create Invoice". Select a client, add line items, and review the preview. You can save as draft, send immediately, or schedule for later.',
    category: 'Billing'
  },
  {
    id: '6',
    question: 'What payment methods are supported?',
    answer: 'The system supports tracking payments via cash, check, credit card, bank transfer, and other methods. Integration with payment processors will be available in a future update.',
    category: 'Billing'
  },
  {
    id: '7',
    question: 'How do I change my password?',
    answer: 'Go to Settings > Security and use the Change Password form. You\'ll need to enter your current password and choose a new secure password that meets our requirements.',
    category: 'Account'
  },
  {
    id: '8',
    question: 'How do I manage notification preferences?',
    answer: 'Navigate to Settings > Notifications. You can toggle email, push, and SMS notifications for different event types like attendance alerts, billing updates, and system notifications.',
    category: 'Account'
  },
  {
    id: '9',
    question: 'Is my data secure?',
    answer: 'Yes! We use industry-standard encryption for data in transit and at rest. All connections are secured with SSL/TLS, and we follow best practices for data security and privacy.',
    category: 'Security'
  },
  {
    id: '10',
    question: 'How do I export my data?',
    answer: 'Data export functionality will be available in Settings > Data & Privacy. You\'ll be able to export your families, attendance records, and billing history in standard formats.',
    category: 'Data'
  }
];

const categories = ['All', 'Getting Started', 'Families', 'Billing', 'Account', 'Security', 'Data'];

const Support: React.FC = () => {
  const { addNotification } = useNotifications();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [expandedFAQ, setExpandedFAQ] = useState<string | null>(null);
  const [contactForm, setContactForm] = useState({
    subject: '',
    message: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const filteredFAQs = faqItems.filter(item => {
    const matchesSearch = searchQuery === '' || 
      item.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.answer.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = selectedCategory === 'All' || item.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const handleContactSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!contactForm.subject || !contactForm.message) {
      addNotification({
        type: 'error',
        title: 'Missing Fields',
        message: 'Please fill in all fields.'
      });
      return;
    }

    setIsSubmitting(true);
    
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    setIsSubmitting(false);
    setSubmitted(true);
    setContactForm({ subject: '', message: '' });
    
    addNotification({
      type: 'success',
      title: 'Message Sent',
      message: 'We\'ll get back to you as soon as possible.'
    });
  };

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      {/* Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-primary-100 rounded-full mb-4">
          <QuestionMarkCircleIcon className="h-8 w-8 text-primary-600" />
        </div>
        <h1 className="heading-lg text-gray-900">Help & Support</h1>
        <p className="mt-2 body-md text-gray-600 max-w-2xl mx-auto">
          Find answers to common questions or get in touch with our support team.
        </p>
      </div>

      {/* Quick Contact Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12">
        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-100 rounded-full mb-4">
            <EnvelopeIcon className="h-6 w-6 text-blue-600" />
          </div>
          <h3 className="font-semibold text-gray-900 mb-1">Email Support</h3>
          <p className="text-sm text-gray-500 mb-2">Get help via email</p>
          <a href="mailto:support@caresync.com" className="text-primary-600 hover:text-primary-700 font-medium text-sm">
            support@caresync.com
          </a>
        </div>

        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 rounded-full mb-4">
            <ChatBubbleLeftRightIcon className="h-6 w-6 text-green-600" />
          </div>
          <h3 className="font-semibold text-gray-900 mb-1">Live Chat</h3>
          <p className="text-sm text-gray-500 mb-2">Mon-Fri, 9am-5pm EST</p>
          <span className="text-gray-400 text-sm">Coming Soon</span>
        </div>

        <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-purple-100 rounded-full mb-4">
            <BookOpenIcon className="h-6 w-6 text-purple-600" />
          </div>
          <h3 className="font-semibold text-gray-900 mb-1">Documentation</h3>
          <p className="text-sm text-gray-500 mb-2">Guides and tutorials</p>
          <span className="text-gray-400 text-sm">Coming Soon</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* FAQ Section */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-900">Frequently Asked Questions</h2>
            </div>

            {/* Search and Filter */}
            <div className="p-4 border-b border-gray-200">
              <div className="flex flex-col sm:flex-row gap-4">
                {/* Search */}
                <div className="flex-1 relative">
                  <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search questions..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                </div>

                {/* Category Filter */}
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  {categories.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* FAQ List */}
            <div className="divide-y divide-gray-200">
              {filteredFAQs.length === 0 ? (
                <div className="p-8 text-center">
                  <QuestionMarkCircleIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500">No questions match your search.</p>
                </div>
              ) : (
                filteredFAQs.map((item) => (
                  <div key={item.id} className="p-4">
                    <button
                      onClick={() => setExpandedFAQ(expandedFAQ === item.id ? null : item.id)}
                      className="w-full flex items-start justify-between text-left"
                    >
                      <div className="flex-1 pr-4">
                        <span className="text-xs font-medium text-primary-600 uppercase tracking-wide">
                          {item.category}
                        </span>
                        <p className="font-medium text-gray-900 mt-1">{item.question}</p>
                      </div>
                      {expandedFAQ === item.id ? (
                        <ChevronUpIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                      ) : (
                        <ChevronDownIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                      )}
                    </button>
                    {expandedFAQ === item.id && (
                      <div className="mt-3 text-gray-600 text-sm pl-0 border-l-2 border-primary-200 ml-0 pl-4">
                        {item.answer}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Contact Form */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden sticky top-8">
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
              <h2 className="text-lg font-semibold text-gray-900">Contact Us</h2>
              <p className="text-sm text-gray-500 mt-1">Can't find what you're looking for?</p>
            </div>

            <div className="p-6">
              {submitted ? (
                <div className="text-center py-8">
                  <CheckCircleIcon className="h-12 w-12 text-green-500 mx-auto mb-4" />
                  <h3 className="font-semibold text-gray-900 mb-2">Message Sent!</h3>
                  <p className="text-sm text-gray-500 mb-4">
                    We typically respond within 24 hours.
                  </p>
                  <button
                    onClick={() => setSubmitted(false)}
                    className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                  >
                    Send another message
                  </button>
                </div>
              ) : (
                <form onSubmit={handleContactSubmit} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Subject
                    </label>
                    <input
                      type="text"
                      value={contactForm.subject}
                      onChange={(e) => setContactForm({ ...contactForm, subject: e.target.value })}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                      placeholder="What can we help with?"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Message
                    </label>
                    <textarea
                      value={contactForm.message}
                      onChange={(e) => setContactForm({ ...contactForm, message: e.target.value })}
                      rows={5}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
                      placeholder="Describe your issue or question..."
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="w-full btn btn-primary justify-center"
                  >
                    {isSubmitting ? (
                      'Sending...'
                    ) : (
                      <>
                        <PaperAirplaneIcon className="h-4 w-4" />
                        Send Message
                      </>
                    )}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Support;
