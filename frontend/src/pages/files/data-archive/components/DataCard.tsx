import React from 'react';
import { 
  HomeIcon, 
  EllipsisVerticalIcon, 
  ArrowTrendingUpIcon 
} from '@heroicons/react/24/outline';

export interface TrendData {
  percentage: number;
  direction: 'up' | 'down';
  label: string;
}

interface DataCardProps {
  name: string;
  value: number;
  trend?: TrendData | null;
  showChart?: boolean;
  chartData?: number[];
  onMenuClick: () => void;
}

const DataCard: React.FC<DataCardProps> = ({
  name,
  value,
  trend,
  showChart = true,
  chartData = [20, 18, 14, 12, 10, 8, 6, 8, 10, 8],
  onMenuClick
}) => {
  const formattedValue = value.toLocaleString();
  
  const getChartPath = () => {
    if (!chartData.length) return '';
    
    const width = 80;
    const height = 40;
    const points = chartData.length;
    const stepX = width / (points - 1);
    
    // Normalize data to fit chart height
    const max = Math.max(...chartData);
    const min = Math.min(...chartData);
    const range = max - min || 1;
    
    const pathPoints = chartData.map((chartValue, index) => {
      const x = index * stepX;
      const y = height - ((chartValue - min) / range) * (height - 8) - 4;
      return `${x} ${y}`;
    }).join(' ');
    
    return `M${pathPoints.replace(/ /g, 'L').substring(1)}`;
  };

  return (
    <div className="card w-full" style={{ height: '200px' }}>
      <div className="card-body p-6 h-full flex flex-col justify-between">
        {/* Header Row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <HomeIcon className="h-6 w-6 text-gray-600" />
            <span className="text-base font-medium text-gray-900">{name}</span>
          </div>
          <button 
            className="text-gray-400 hover:text-gray-600" 
            onClick={onMenuClick}
          >
            <EllipsisVerticalIcon className="h-5 w-5" />
          </button>
        </div>
        
        {/* Content Area */}
        <div className="flex items-end justify-between mt-8">
          {/* Left Side - Number and Trend */}
          <div className="flex flex-col">
            <div className="text-4xl font-bold text-gray-900 leading-none mb-2">
              {formattedValue}
            </div>
            {trend && (
              <div className="flex items-center space-x-1">
                <ArrowTrendingUpIcon 
                  className={`h-4 w-4 ${
                    trend.direction === 'up' ? 'text-green-600' : 'text-red-600'
                  }`} 
                />
                <span 
                  className={`text-sm ${
                    trend.direction === 'up' ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {trend.percentage}% {trend.label}
                </span>
              </div>
            )}
          </div>
          
          {/* Right Side - Line Chart */}
          {showChart && (
            <div className="flex-shrink-0">
              <svg width="80" height="40" viewBox="0 0 80 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path 
                  d={getChartPath()} 
                  stroke={trend?.direction === 'up' ? '#10B981' : '#EF4444'} 
                  strokeWidth="2.5" 
                  fill="none" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                />
              </svg>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DataCard;
