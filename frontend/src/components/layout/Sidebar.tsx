import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import logoWithBg from '../../assets/images/svgs/Logo_with_bg.svg';
import {
  DocumentTextIcon,
  UserGroupIcon,
  UsersIcon,
  BellIcon,
  Cog6ToothIcon,
  LifebuoyIcon,
  CurrencyDollarIcon,
  ArrowRightOnRectangleIcon,
  ClockIcon,
  CalendarDaysIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

// Custom Dashboard icon matching Hugeicons dashboard-square design
const DashboardIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="3" y="3" width="8" height="8" rx="2" />
    <rect x="13" y="3" width="8" height="8" rx="2" />
    <rect x="3" y="13" width="8" height="8" rx="2" />
    <rect x="13" y="13" width="8" height="8" rx="2" />
  </svg>
);

const mainNavigationItems = [
  { 
    name: 'Dashboard', 
    to: '/dashboard', 
    icon: DashboardIcon,
  },
  { 
    name: 'My Files', 
    to: '/files', 
    icon: DocumentTextIcon,
  },
  { 
    name: 'Families', 
    to: '/families', 
    icon: UserGroupIcon,
  },
  { 
    name: 'Children', 
    to: '/children', 
    icon: UsersIcon,
  },
  { 
    name: 'Invoicing', 
    to: '/invoicing', 
    icon: CurrencyDollarIcon,
  },
  { 
    name: 'Scheduling', 
    to: '/scheduling', 
    icon: CalendarDaysIcon,
  },
  { 
    name: 'Letterhead Creator', 
    to: '/letterhead', 
    icon: EnvelopeIcon,
  },
  { 
    name: 'Activity Log', 
    to: '/activity', 
    icon: ClockIcon,
  },
];

const bottomNavigationItems = [
  { 
    name: 'Notifications', 
    to: '/notifications', 
    icon: BellIcon,
  },
  { 
    name: 'Settings', 
    to: '/settings', 
    icon: Cog6ToothIcon,
  },
  { 
    name: 'Support', 
    to: '/support', 
    icon: LifebuoyIcon,
  },
];

const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { state: authState, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActiveRoute = (path: string) => {
    // Handle nested routes for files section
    if (path === '/files') {
      return location.pathname.startsWith('/files');
    }
    // Handle nested routes for families section
    if (path === '/families') {
      return location.pathname.startsWith('/families') || location.pathname === '/sibling-assignment';
    }
    // Handle nested routes for children section
    if (path === '/children') {
      return location.pathname.startsWith('/children');
    }
    // Handle invoicing section
    if (path === '/invoicing') {
      return location.pathname.startsWith('/invoicing');
    }
    // Handle activity section
    if (path === '/activity') {
      return location.pathname.startsWith('/activity');
    }
    return location.pathname === path;
  };

  const getUserInitials = () => {
    if (!authState.user) return 'AD';
    const first = authState.user.firstName?.[0] || 'A';
    const last = authState.user.lastName?.[0] || 'D';
    return (first + last).toUpperCase();
  };

  return (
    <div className="w-64 bg-white border-r border-gray-200 flex-shrink-0 transition-all duration-300 ease-in-out no-print">
      {/* Mobile overlay */}
      <div 
        className={`fixed inset-0 bg-black bg-opacity-50 md:hidden z-40 ${open ? 'block' : 'hidden'}`}
        onClick={onClose}
      />
      
      {/* Sidebar Content */}
      <div className="relative h-full flex flex-col overflow-hidden">
        {/* Logo Section */}
        <div className="flex items-center px-4 py-4">
          <div className="flex items-center space-x-3">
            <img 
              src={logoWithBg} 
              alt="CareSync"
              className="h-10 w-auto"
            />
            <span className="logo-text">
              CareSync
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-4 py-4 space-y-1">
          {mainNavigationItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                to={item.to}
                className={`nav-item ${isActiveRoute(item.to) ? 'nav-item--active' : ''}`}
              >
                <Icon className="w-5 h-5" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Bottom Navigation */}
        <div className="px-4 py-4 space-y-1">
          {bottomNavigationItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.name}
                to={item.to}
                className={`nav-item nav-item--bottom ${isActiveRoute(item.to) ? 'nav-item--active' : ''}`}
              >
                <Icon className="w-5 h-5" />
                {item.name}
              </Link>
            );
          })}
        </div>
        
        <div className="border-t border-gray-200 divider"></div>
        
        {/* User Profile */}
        <div className="px-4 py-4">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center">
              <span className="text-white text-sm font-medium">{getUserInitials()}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="user-name">
                {authState.user ? `${authState.user.firstName} ${authState.user.lastName}` : 'Admin User'}
              </p>
              <p className="text-xs text-gray-500 truncate">
                {authState.user?.email || 'admin@company.com'}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              title="Logout"
            >
              <ArrowRightOnRectangleIcon className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
