import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Bars3Icon, MagnifyingGlassIcon, BuildingOffice2Icon } from '@heroicons/react/24/outline';
// import { ArrowUpTrayIcon } from '@heroicons/react/24/solid';
import { useAuth } from '../../context/AuthContext';
import { config } from '../../config';

interface HeaderProps {
  onToggleSidebar: () => void;
}

interface Breadcrumb {
  label: string;
  to?: string;
}

const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const location = useLocation();
  const { state } = useAuth();
  const organization = state.organization;

  const formatBreadcrumbLabel = (segment: string): string => {
    return segment
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const getBreadcrumbs = (): Breadcrumb[] => {
    const routePath = location.pathname;
    const pathSegments = routePath.split('/').filter(segment => segment);

    if (pathSegments.length === 0) return [];

    const crumbs: Breadcrumb[] = [];
    let currentPath = '';

    for (let i = 0; i < pathSegments.length; i++) {
      currentPath += '/' + pathSegments[i];
      const isLast = i === pathSegments.length - 1;

      crumbs.push({
        label: formatBreadcrumbLabel(pathSegments[i]),
        to: isLast ? undefined : currentPath
      });
    }

    return crumbs;
  };

  const breadcrumbs = getBreadcrumbs();

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
    // Implement search functionality
    console.log('Searching for:', e.target.value);
  };

  // const handleUploadClick = () => {
  //   // Implement upload functionality
  //   console.log('Upload files clicked');
  // };

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="flex items-center justify-between py-3 px-3">
        {/* Left side - Breadcrumb */}
        <div className="flex items-center">
          <button
            onClick={onToggleSidebar}
            className="p-2 rounded-md hover:bg-gray-100 focus:outline-none mr-3"
          >
            <Bars3Icon className="h-5 w-5 text-gray-600" />
          </button>

          <nav className="flex items-center font-comfortaa text-sm font-normal">
            <Link to="/" className="text-gray-400 hover:text-gray-600 transition-colors">
              Home
            </Link>
            {breadcrumbs.length > 0 && (
              <svg className="w-4 h-4 mx-2 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            )}
            {breadcrumbs.map((crumb, index) => (
              <React.Fragment key={index}>
                {crumb.to ? (
                  <Link
                    to={crumb.to}
                    className="text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-gray-700 font-medium">
                    {crumb.label}
                  </span>
                )}
                {index < breadcrumbs.length - 1 && (
                  <svg className="w-4 h-4 mx-2 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </React.Fragment>
            ))}
          </nav>
        </div>

        {/* Center - Search Bar */}
        <div className="flex items-center space-x-4">
          <div className="relative w-[40rem]">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearch}
              className="w-full py-3 pl-10 pr-4 border border-gray-300 rounded-lg font-comfortaa text-sm bg-white text-gray-900 placeholder-gray-400 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="Search for attendance files, claims or reports ..."
            />
          </div>
        </div>

        {/* Right side - Org Logo + Upload Button */}
        <div className="flex items-center space-x-4">
          {/* Organization Logo/Badge */}
          {organization && (
            <div className="flex items-center space-x-2 px-3 py-1.5 bg-gray-50 rounded-lg border border-gray-200">
              {organization.logo_url ? (
                <img 
                  src={config.getUploadUrl(organization.logo_url)}
                  alt={organization.name} 
                  className="h-7 w-7 rounded object-contain"
                />
              ) : (
                <div className="h-7 w-7 rounded bg-primary-100 flex items-center justify-center">
                  <BuildingOffice2Icon className="h-4 w-4 text-primary-600" />
                </div>
              )}
              <span className="text-sm font-medium text-gray-700 max-w-[120px] truncate">
                {organization.name}
              </span>
            </div>
          )}
{/*           
          <button
            onClick={handleUploadClick}
            className="btn btn-secondary"
          >
            <ArrowUpTrayIcon className="h-5 w-5" />
            Upload Files
          </button> */}
        </div>
      </div>
    </header>
  );
};

export default Header;
