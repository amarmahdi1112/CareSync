// ============================================
// Child Card Components for List View
// Clean, minimal design matching FamilyDetail
// ============================================

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRightIcon } from '@heroicons/react/24/outline';
import { AgeGroupBadge, StatusBadge } from '../../../../components/ui';
import type { ChildListItem } from '../../types';
import { calculateAge } from '../../types';

// -------------------- Child Card (Grid View) --------------------

interface ChildCardProps {
  child: ChildListItem;
  onClick?: () => void;
}

export const ChildCard: React.FC<ChildCardProps> = ({ child, onClick }) => {
  const navigate = useNavigate();
  const initials = `${child.firstName[0]}${child.lastName[0]}`;
  const age = calculateAge(child.dateOfBirth);
  
  return (
    <div
      onClick={onClick}
      className="group bg-white rounded-xl border border-gray-200 p-4 hover:shadow-lg hover:border-primary-300 hover:-translate-y-0.5 transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {/* Avatar with initials */}
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-lg font-bold ${
            child.status === 'active' 
              ? 'bg-gradient-to-br from-primary-100 to-primary-200 text-primary-600' 
              : 'bg-gray-100 text-gray-400'
          }`}>
            {initials}
          </div>
          <div>
            <h4 className="font-semibold text-gray-900 group-hover:text-primary-600 transition-colors">
              {child.firstName} {child.lastName}
            </h4>
            <div className="flex items-center gap-2 mt-1">
              <AgeGroupBadge ageGroup={child.ageGroup} />
              <span className="text-xs text-gray-500">{age}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {child.status === 'active' ? (
            <span className="w-2 h-2 rounded-full bg-green-500" title="Active" />
          ) : (
            <span className="w-2 h-2 rounded-full bg-gray-300" title="Inactive" />
          )}
          <ChevronRightIcon className="w-5 h-5 text-gray-300 group-hover:text-primary-500 transition-colors" />
        </div>
      </div>
      
      {/* Footer */}
      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
        <button
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/families/${child.familyId}`);
          }}
          className="text-sm text-gray-500 hover:text-primary-600 transition-colors"
        >
          {child.familyName}
        </button>
        <span className="text-xs text-gray-400">
          {new Date(child.enrollmentDate).toLocaleDateString()}
        </span>
      </div>
    </div>
  );
};

// -------------------- Child Row (Table View) --------------------

interface ChildRowProps {
  child: ChildListItem;
  onClick?: () => void;
}

export const ChildRow: React.FC<ChildRowProps> = ({ child, onClick }) => {
  const navigate = useNavigate();
  const initials = `${child.firstName[0]}${child.lastName[0]}`;
  
  return (
    <tr
      onClick={onClick}
      className="hover:bg-gray-50 cursor-pointer transition-colors"
    >
      <td className="px-6 py-4 whitespace-nowrap">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold ${
            child.status === 'active' 
              ? 'bg-gradient-to-br from-primary-100 to-primary-200 text-primary-600' 
              : 'bg-gray-100 text-gray-400'
          }`}>
            {initials}
          </div>
          <div>
            <div className="font-medium text-gray-900">{child.firstName} {child.lastName}</div>
            <div className="text-sm text-gray-500">DOB: {new Date(child.dateOfBirth).toLocaleDateString()}</div>
          </div>
        </div>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <AgeGroupBadge ageGroup={child.ageGroup} />
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <button
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/families/${child.familyId}`);
          }}
          className="text-sm text-primary-600 hover:text-primary-700 hover:underline font-medium"
        >
          {child.familyName}
        </button>
      </td>
      <td className="px-6 py-4 whitespace-nowrap">
        <StatusBadge status={child.status} />
      </td>
      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
        {new Date(child.enrollmentDate).toLocaleDateString()}
      </td>
    </tr>
  );
};

export default ChildCard;
