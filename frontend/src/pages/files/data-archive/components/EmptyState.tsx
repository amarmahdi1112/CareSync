import React from 'react';
import dataEmptyImage from '../../../../assets/images/pngs/Data_empty.png';

interface EmptyStateProps {
  onUploadClick: () => void;
}

const EmptyState: React.FC<EmptyStateProps> = ({ onUploadClick }) => {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {/* Database Icon */}
      <div className="mb-8">
        <img 
          src={dataEmptyImage} 
          alt="No data available" 
          className="w-[180px] h-[180px] object-contain"
        />
      </div>
      
      {/* Text Content */}
      <div className="text-center max-w-md">
        <h3 className="text-xl font-semibold text-gray-900 mb-3">
          You have no data available yet!
        </h3>
        <p className="text-gray-600 mb-8 leading-relaxed">
          You haven't uploaded any files yet. Just upload your documents to access our powerful features.
        </p>
        
        {/* Upload Button */}
        <button 
          className="btn btn-primary btn-lg"
          onClick={onUploadClick}
        >
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
          </svg>
          Upload Files
        </button>
      </div>
    </div>
  );
};

export default EmptyState;
