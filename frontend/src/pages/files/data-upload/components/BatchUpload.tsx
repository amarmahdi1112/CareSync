/* eslint-disable @typescript-eslint/no-unused-vars */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import FileUpload from './FileUpload';

const BatchUpload: React.FC = () => {
  const navigate = useNavigate();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedDate, setSelectedDate] = useState('');
  const [batchName, setBatchName] = useState('');
  const [_isUploading, setIsUploading] = useState(false);

  const goBackToEmpty = () => {
    navigate('/files/data-upload');
  };

  const handleFileSelected = (files: File[]) => {
    setSelectedFiles(files);
    console.log('Files selected:', files.map(f => f.name));
  };

  const handleUploadStart = () => {
    setIsUploading(true);
    console.log('Batch upload started');
  };

  const handleUploadComplete = () => {
    setIsUploading(false);
    console.log('Batch upload completed');
  };

  const handleUploadError = (error: string) => {
    setIsUploading(false);
    console.error('Batch upload error:', error);
  };

  const handleContinue = () => {
    if (selectedFiles.length > 0) {
      console.log('Continuing with batch upload...', {
        files: selectedFiles.map(f => f.name),
        date: selectedDate,
        batchName: batchName
      });
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
          Batch Upload
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
      
      {/* Date Field */}
      <div className="space-y-2">
        <label className="flex items-center space-x-2 text-sm font-medium text-gray-700">
          <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
          </svg>
          <span>Date (MM/YYYY)</span>
        </label>
        <input 
          type="month"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          placeholder="Pick a Date"
          className="input"
        />
        <p className="text-sm text-gray-500">This will assist in organizing your files according to their timelines.</p>
      </div>
      
      <FileUpload 
        acceptedTypes={['csv']}
        maxSize={52428800}
        multiple={true}
        headerLabel="Upload File"
        title="Upload multiple files"
        description="Drag and drop multiple CSV files here, or click to browse"
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
            <path d="M10.8748 14.25H9.37477C7.25302 14.25 6.19252 14.25 5.53402 13.5908C4.87402 12.9323 4.87402 11.871 4.87402 9.75V6C4.87402 3.879 4.87402 2.81775 5.53402 2.15925C6.19177 1.5 7.25227 1.5 9.37402 1.5H10.382C10.9955 1.5 11.3015 1.5 11.5775 1.614C11.8528 1.728 12.0695 1.9455 12.503 2.379L14.4958 4.371C14.9293 4.8045 15.146 5.022 15.2608 5.29725C15.3748 5.57325 15.3748 5.87925 15.3748 6.49275V9.75C15.3748 11.871 15.3748 12.9323 14.7155 13.5908C14.057 14.25 12.9958 14.25 10.8748 14.25Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M11.25 1.875V2.625C11.25 4.0395 11.25 4.746 11.6895 5.1855C12.1283 5.625 12.8355 5.625 14.25 5.625H15M4.875 3.75C4.27826 3.75 3.70597 3.98705 3.28401 4.40901C2.86205 4.83097 2.625 5.40326 2.625 6V12C2.625 14.121 2.625 15.1823 3.2835 15.8408C3.94275 16.5 5.00325 16.5 7.125 16.5H10.875C11.4717 16.5 12.044 16.2629 12.466 15.841C12.8879 15.419 13.125 14.8467 13.125 14.25M7.5 8.25H10.5M7.5 11.25H12.75" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        }
        buttonIcon={
          <img src="/src/assets/images/svgs/file-upload_white_bg.svg" alt="Upload" className="h-4 w-4" />
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
      
      {/* Upload Instructions */}
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          To upload a CSV file, click the Browse File button and select your CSV file from your device. Ensure that your file is formatted correctly.
        </p>
        
        {/* Batch Name Field */}
        <div className="space-y-2">
          <label className="flex items-center space-x-2 text-sm font-medium text-gray-700">
            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a1.994 1.994 0 01-1.414.586H7a4 4 0 01-4-4v-9a4 4 0 014-4z"/>
            </svg>
            <span>Batch Name (Optional)</span>
          </label>
          <input 
            type="text"
            value={batchName}
            onChange={(e) => setBatchName(e.target.value)}
            placeholder="e.g., December 2024 Batch"
            className="input"
          />
          <p className="text-sm text-gray-500">
            You can enter a batch name here to help categorize your files. This is optional, but providing a descriptive name can make it easier to identify and manage your files later.
          </p>
        </div>
      </div>
      
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
          disabled={selectedFiles.length === 0}
        >
          Continue
        </button>
      </div>
    </div>
  );
};

export default BatchUpload;
