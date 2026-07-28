/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  FunnelIcon, 
  CalendarDaysIcon, 
  ArrowPathIcon 
} from '@heroicons/react/24/outline';
import { format } from 'date-fns';
import DataCard from './components/DataCard';
import EmptyState from './components/EmptyState';

const DataArchiveView: React.FC = () => {
  const navigate = useNavigate();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  const [dateRange] = useState({
    start: new Date(2025, 0, 6), // Jan 6, 2025
    end: new Date(2025, 0, 13), // Jan 13, 2025
  });

  const tabs = [
    { key: 'all', name: 'All files' },
    { key: 'records', name: 'Record files' },
    { key: 'registration', name: 'Registration files' },
  ];

  const dataCards = [
    {
      id: 1,
      name: 'Betalihem (Bethy) Ebobi',
      value: 2420,
      trend: {
        percentage: 40,
        direction: 'up' as const,
        label: 'vs last month',
      },
      showChart: true,
      chartData: [20, 18, 14, 12, 10, 8, 6, 8, 10, 8],
    },
    // Add more cards as needed
  ];

  const formatDateRange = (start: Date, end: Date) => {
    return `${format(start, 'MMM d, yyyy')} - ${format(end, 'MMM d, yyyy')}`;
  };

  const refreshData = async () => {
    setIsRefreshing(true);
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 1000));
      // Refresh data logic here
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleCardMenu = (card: any) => {
    console.log('Card menu clicked:', card);
  };

  const handleUploadClick = () => {
    // Navigate to upload page
    window.location.href = '/files/data-upload';
  };

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Data Archive</h1>
            <p className="mt-2 text-sm text-gray-600">
              Effortlessly view and organize your attendance records with ease and sophistication.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button className="btn btn-secondary">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="mr-2">
                <path d="M10.0002 17.9167C13.7321 17.9167 15.5981 17.9167 16.7575 16.7573C17.9168 15.5979 17.9168 13.7319 17.9168 10C17.9168 6.26804 17.9168 4.40207 16.7575 3.2427C15.5981 2.08334 13.7321 2.08334 10.0002 2.08334C6.26821 2.08334 4.40224 2.08334 3.24286 3.2427C2.0835 4.40208 2.0835 6.26805 2.0835 10C2.0835 13.7319 2.0835 15.5979 3.24286 16.7573C4.40223 17.9167 6.2682 17.9167 10.0002 17.9167Z" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12.5 7.5L7.5 12.4997M12.5 12.5L7.5 7.50033" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Generate Schedule
            </button>
            <button 
              onClick={() => navigate('/files/claim-generation')}
              className="btn btn-primary"
            >
              Generate Claim
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="ml-2">
                <path d="M13.3332 10H6.6665M13.3332 10C13.3332 9.4165 11.6713 8.32627 11.2498 7.91666M13.3332 10C13.3332 10.5835 11.6713 11.6737 11.2498 12.0833" stroke="#F7F2FA" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M2.0835 10C2.0835 6.26805 2.0835 4.40208 3.24286 3.2427C4.40224 2.08334 6.26821 2.08334 10.0002 2.08334C13.7321 2.08334 15.5981 2.08334 16.7575 3.2427C17.9168 4.40208 17.9168 6.26805 17.9168 10C17.9168 13.7319 17.9168 15.5979 16.7575 16.7573C15.5981 17.9167 13.7321 17.9167 10.0002 17.9167C6.26821 17.9167 4.40224 17.9167 3.24286 16.7573C2.0835 15.5979 2.0835 13.7319 2.0835 10Z" stroke="#F7F2FA" strokeWidth="1.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Filter Controls */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button className="btn btn-secondary">
              <FunnelIcon className="h-5 w-5 mr-2" />
              Filters
            </button>
            
            {/* Date Range Picker */}
            <div className="flex items-center space-x-2 px-4 py-2 border border-gray-300 rounded-lg bg-white">
              <CalendarDaysIcon className="h-5 w-5 text-gray-400" />
              <span className="text-sm text-gray-700">{formatDateRange(dateRange.start, dateRange.end)}</span>
            </div>
          </div>
          
          <button onClick={refreshData} className="btn btn-secondary">
            <ArrowPathIcon className={`h-5 w-5 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="mb-6">
        <nav className="flex space-x-8" aria-label="Tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`
                whitespace-nowrap border-b-2 font-medium py-2 px-1 text-sm transition-colors
                ${activeTab === tab.key
                  ? 'border-purple-500 text-purple-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }
              `}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Data Cards Grid or Empty State */}
      {dataCards.length > 0 ? (
        <div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3" style={{ gap: '24px' }}>
            {dataCards.map((card) => (
              <DataCard
                key={card.id}
                name={card.name}
                value={card.value}
                trend={card.trend}
                showChart={card.showChart}
                chartData={card.chartData}
                onMenuClick={() => handleCardMenu(card)}
              />
            ))}
          </div>
        </div>
      ) : (
        <EmptyState onUploadClick={handleUploadClick} />
      )}
    </div>
  );
};

export default DataArchiveView;
