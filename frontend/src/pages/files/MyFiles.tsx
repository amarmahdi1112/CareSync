import React from 'react';
import { Link, useLocation, Outlet } from 'react-router-dom';
import { 
  ArchiveBoxIcon,
  CloudArrowUpIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';

const navigationTabs = [
  {
    name: 'Data Archive',
    route: '/data-archive',
    icon: ArchiveBoxIcon,
  },
  {
    name: 'Data Upload',
    route: '/data-upload',
    icon: CloudArrowUpIcon,
  },
  {
    name: 'Data Viewing',
    route: '/data-viewing',
    icon: ChartBarIcon,
  },
];

const MyFiles: React.FC = () => {
  const location = useLocation();

  return (
    <div>
      {/* Navigation tabs for child views */}
      <div className="mb-6">
        <nav className="flex space-x-8" aria-label="Tabs">
          {navigationTabs.map((tab) => {
            const isActive = location.pathname === `/files${tab.route}`;
            return (
              <Link
                key={tab.route}
                to={`/files${tab.route}`}
                className={`
                  whitespace-nowrap py-2 px-1 border-b-2 font-medium text-sm transition-colors
                  ${isActive
                    ? 'border-purple-500 text-purple-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }
                `}
              >
                <tab.icon className="h-5 w-5 inline mr-2" />
                {tab.name}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Child view container */}
      <div>
        <Outlet />
      </div>
    </div>
  );
};

export default MyFiles;
