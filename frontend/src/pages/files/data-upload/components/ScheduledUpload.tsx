/* eslint-disable @typescript-eslint/no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import FileUpload from './FileUpload';

const ScheduledUpload: React.FC = () => {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [_isUploading, setIsUploading] = useState(false);

  const goBackToEmpty = () => {
    navigate('/files/data-upload');
  };

  const handleFileSelected = (files: File[]) => {
    setSelectedFile(files[0] || null);
    console.log('Scheduled upload file selected:', files[0]?.name);
  };

  const handleUploadStart = () => {
    setIsUploading(true);
    console.log('Scheduled upload started');
  };

  const handleUploadComplete = () => {
    setIsUploading(false);
    console.log('Scheduled upload completed');
  };

  const handleUploadError = (error: string) => {
    setIsUploading(false);
    console.error('Scheduled upload error:', error);
  };

  const handleContinue = () => {
    if (selectedFile) {
      console.log('Continuing with scheduled upload...', selectedFile.name);
      // Add your continue logic here
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 style={{ 
          color: 'var(--Foundation-Green-Normal, #033B4D)', 
          fontFamily: 'var(--FontFamily, Comfortaa)', 
          fontSize: 'var(--FontSize-H7_FontSize, 24px)', 
          fontWeight: 700, 
          lineHeight: 'var(--LineHeight-H7_LineHeight, 28px)' 
        }}>
          Scheduled Upload
        </h2>
        <button 
          className="btn btn-secondary btn-sm"
          onClick={goBackToEmpty}
        >
          <svg className="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
          </svg>
          Back
        </button>
      </div>
      
      <FileUpload 
        acceptedTypes={['csv']}
        maxSize={52428800}
        multiple={false}
        headerLabel="Upload File"
        title="Set up automated uploads"
        description="Configure automatic file uploads on a schedule"
        onFileSelected={handleFileSelected}
        onUploadStart={handleUploadStart}
        onUploadComplete={handleUploadComplete}
        onUploadError={handleUploadError}
        headerIcon={
          <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
        }
        uploadIcon={
          <svg className="h-12 w-12 text-gray-400" width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 1.5V4.5M6 1.5V4.5M2.25 7.5H15.75M9.75 3H8.25C5.42175 3 4.00725 3 3.129 3.879C2.25075 4.758 2.25 6.17175 2.25 9V10.5C2.25 13.3282 2.25 14.7427 3.129 15.621C4.008 16.4992 5.42175 16.5 8.25 16.5H9.75C12.5782 16.5 13.9927 16.5 14.871 15.621C15.7492 14.742 15.75 13.3282 15.75 10.5V9C15.75 6.17175 15.75 4.75725 14.871 3.879C13.992 3.00075 12.5782 3 9.75 3Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        }
        buttonIcon={
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"/>
          </svg>
        }
        fileIcon={
          <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
        }
        removeIcon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/>
          </svg>
        }
        errorIcon={
          <svg className="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        }
      />
      
      {/* Action Buttons */}
      <div className="flex justify-end space-x-4 mt-8">
        <button 
          className="btn btn-secondary"
          onClick={goBackToEmpty}
        >
          Cancel
        </button>
        <button 
          className="btn btn-primary"
          onClick={handleContinue}
          disabled={!selectedFile}
        >
          Continue
        </button>
      </div>
    </div>
  );
};

export default ScheduledUpload;
