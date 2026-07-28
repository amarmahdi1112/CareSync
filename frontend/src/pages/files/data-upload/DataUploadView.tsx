/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useRef, useEffect } from 'react';
import { useLocation, Outlet } from 'react-router-dom';
import uploadEmptyImage from '../../../assets/images/pngs/Upload_empty.png';

const DataUploadView: React.FC = () => {
  const location = useLocation();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Mock data - in real app this would come from a store or API
  const [uploadedFiles] = useState<any[]>([
    {
      id: 1,
      name: 'Betalihem_Ebobi_Attendance.csv',
      type: 'batch-upload',
      size: 2048576, // 2MB
      status: 'completed',
      uploadDate: new Date('2025-01-15T10:30:00'),
      selectedDate: '2025-01',
      batchName: 'January 2025 Batch'
    },
    {
      id: 2,
      name: 'Sarah_Johnson_Attendance.csv',
      type: 'batch-upload',
      size: 1536000, // 1.5MB
      status: 'completed',
      uploadDate: new Date('2025-01-15T10:30:00'),
      selectedDate: '2025-01',
      batchName: 'January 2025 Batch'
    },
    {
      id: 3,
      name: 'Michael_Smith_Attendance.csv',
      type: 'batch-upload',
      size: 1792000, // 1.7MB
      status: 'uploading',
      uploadDate: new Date('2025-01-15T10:30:00'),
      selectedDate: '2025-01',
      batchName: 'January 2025 Batch'
    },
    {
      id: 4,
      name: 'Individual_Report.csv',
      type: 'single-csv',
      size: 512000, // 512KB
      status: 'completed',
      uploadDate: new Date('2025-01-14T14:20:00')
    },
    {
      id: 5,
      name: 'Monthly_Summary.csv',
      type: 'scheduled-upload',
      size: 768000, // 768KB
      status: 'error',
      uploadDate: new Date('2025-01-13T09:15:00')
    }
  ]);
  const hasUploadedFiles = uploadedFiles.length > 0;
  const hasActiveRoute = location.pathname !== '/files/data-upload';

  const uploadOptions = [
    {
      id: 'single-csv',
      title: 'Single CSV Upload',
      description: 'Upload one CSV file at a time',
      icon: (
        <svg width="14" height="18" viewBox="0 0 14 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M1 9V10.908C1 13.3417 1 14.559 1.6645 15.3832C1.7987 15.5497 1.95032 15.7013 2.11675 15.8355C2.9425 16.5 4.15825 16.5 6.592 16.5C7.12075 16.5 7.3855 16.5 7.62775 16.4145C7.67775 16.3965 7.727 16.376 7.7755 16.353C8.008 16.242 8.19475 16.0553 8.569 15.681L12.121 12.129C12.5552 11.6955 12.7712 11.4788 12.886 11.2028C13 10.9268 13 10.6208 13 10.0073V7.5C13 4.67175 13 3.25725 12.121 2.379C11.242 1.50075 9.82825 1.5 7 1.5M7.75 16.125V15.75C7.75 13.629 7.75 12.5677 8.40925 11.9092C9.06775 11.25 10.129 11.25 12.25 11.25H12.625" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5.5 3.75C5.0575 3.29475 3.88 1.5 3.25 1.5C2.62 1.5 1.4425 3.29475 1 3.75M3.25 2.25V7.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    },
    {
      id: 'batch-upload',
      title: 'Batch Upload',
      description: 'Upload multiple files at once',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M10.8748 14.25H9.37477C7.25302 14.25 6.19252 14.25 5.53402 13.5908C4.87402 12.9323 4.87402 11.871 4.87402 9.75V6C4.87402 3.879 4.87402 2.81775 5.53402 2.15925C6.19177 1.5 7.25227 1.5 9.37402 1.5H10.382C10.9955 1.5 11.3015 1.5 11.5775 1.614C11.8528 1.728 12.0695 1.9455 12.503 2.379L14.4958 4.371C14.9293 4.8045 15.146 5.022 15.2608 5.29725C15.3748 5.57325 15.3748 5.87925 15.3748 6.49275V9.75C15.3748 11.871 15.3748 12.9323 14.7155 13.5908C14.057 14.25 12.9958 14.25 10.8748 14.25Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M11.25 1.875V2.625C11.25 4.0395 11.25 4.746 11.6895 5.1855C12.1283 5.625 12.8355 5.625 14.25 5.625H15M4.875 3.75C4.27826 3.75 3.70597 3.98705 3.28401 4.40901C2.86205 4.83097 2.625 5.40326 2.625 6V12C2.625 14.121 2.625 15.1823 3.2835 15.8408C3.94275 16.5 5.00325 16.5 7.125 16.5H10.875C11.4717 16.5 12.044 16.2629 12.466 15.841C12.8879 15.419 13.125 14.8467 13.125 14.25M7.5 8.25H10.5M7.5 11.25H12.75" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    },
    {
      id: 'scheduled-upload',
      title: 'Scheduled Upload',
      description: 'Set up automated uploads',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 1.5V4.5M6 1.5V4.5M2.25 7.5H15.75M9.75 3H8.25C5.42175 3 4.00725 3 3.129 3.879C2.25075 4.758 2.25 6.17175 2.25 9V10.5C2.25 13.3282 2.25 14.7427 3.129 15.621C4.008 16.4992 5.42175 16.5 8.25 16.5H9.75C12.5782 16.5 13.9927 16.5 14.871 15.621C15.7492 14.742 15.75 13.3282 15.75 10.5V9C15.75 6.17175 15.75 4.75725 14.871 3.879C13.992 3.00075 12.5782 3 9.75 3Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    }
  ];

  const toggleDropdown = () => {
    setShowDropdown(!showDropdown);
  };

  const navigateToUpload = (uploadType: string) => {
    window.location.href = `/files/data-upload/${uploadType}`;
    setShowDropdown(false);
  };

  const handleClickOutside = (event: MouseEvent) => {
    if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
      setShowDropdown(false);
    }
  };

  useEffect(() => {
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, []);

  // Utility functions
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (date: Date): string => {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  const formatFileType = (type: string): string => {
    const typeMap: Record<string, string> = {
      'single-csv': 'Single CSV',
      'batch-upload': 'Batch Upload',
      'scheduled-upload': 'Scheduled'
    };
    return typeMap[type] || type;
  };

  const formatStatus = (status: string): string => {
    const statusMap: Record<string, string> = {
      'uploading': 'Uploading',
      'completed': 'Completed',
      'error': 'Error'
    };
    return statusMap[status] || status;
  };

  const getTypeClass = (type: string): string => {
    const classMap: Record<string, string> = {
      'single-csv': 'bg-primary-100 text-primary-700',
      'batch-upload': 'bg-green-100 text-green-800',
      'scheduled-upload': 'bg-purple-100 text-purple-800'
    };
    return classMap[type] || 'bg-gray-100 text-gray-800';
  };

  const getStatusClass = (status: string): string => {
    const classMap: Record<string, string> = {
      'uploading': 'bg-yellow-100 text-yellow-800',
      'completed': 'bg-green-100 text-green-800',
      'error': 'bg-red-100 text-red-800'
    };
    return classMap[status] || 'bg-gray-100 text-gray-800';
  };

  const getBatchFiles = () => {
    const batchFiles = uploadedFiles.filter(f => f.type === 'batch-upload');
    const grouped = batchFiles.reduce((acc: Record<string, any[]>, file) => {
      const key = file.batchName || 'Unnamed Batch';
      if (!acc[key]) acc[key] = [];
      acc[key].push(file);
      return acc;
    }, {});
    return Object.entries(grouped);
  };

  const getNonBatchFiles = () => {
    return uploadedFiles.filter(f => f.type !== 'batch-upload');
  };

  const getBatchStats = (batchFiles: any[]) => {
    return {
      completed: batchFiles.filter(f => f.status === 'completed').length,
      uploading: batchFiles.filter(f => f.status === 'uploading').length,
      error: batchFiles.filter(f => f.status === 'error').length
    };
  };

  const formatBatchDate = (dateString: string): string => {
    if (!dateString) return 'Unknown';
    const [year, month] = dateString.split('-');
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];
    return `${monthNames[parseInt(month) - 1]} ${year}`;
  };

  const downloadFile = (file: any) => {
    console.log('Downloading file:', file.name);
    // Implement actual download logic here
  };

  const removeUploadedFile = (fileId: number) => {
    console.log('Removing uploaded file:', fileId);
    // Implement file removal logic here
  };

  return (
    <div>
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 style={{ 
              color: 'var(--Foundation-Green-Normal, #033B4D)', 
              fontFamily: 'var(--FontFamily, Comfortaa)', 
              fontSize: 'var(--FontSize-H7_FontSize, 24px)', 
              fontWeight: 700, 
              lineHeight: 'var(--LineHeight-H7_LineHeight, 28px)' 
            }}>
              Data Upload
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              Upload and manage your attendance and registration files with ease.
            </p>
          </div>
          <div className="flex items-center space-x-3">
            <button className="btn btn-secondary">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="mr-2">
                <path d="M10.0002 17.9167C13.7321 17.9167 15.5981 17.9167 16.7575 16.7573C17.9168 15.5979 17.9168 13.7319 17.9168 10C17.9168 6.26804 17.9168 4.40207 16.7575 3.2427C15.5981 2.08334 13.7321 2.08334 10.0002 2.08334C6.26821 2.08334 4.40224 2.08334 3.24286 3.2427C2.0835 4.40208 2.0835 6.26805 2.0835 10C2.0835 13.7319 2.0835 15.5979 3.24286 16.7573C4.40223 17.9167 6.2682 17.9167 10.0002 17.9167Z" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M12.5 7.5L7.5 12.4997M12.5 12.5L7.5 7.50033" stroke="#6F6B6C" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Download Template
            </button>
            
            {/* Upload Files Dropdown */}
            <div className="relative" ref={dropdownRef}>
              <button 
                className="btn btn-primary"
                onClick={toggleDropdown}
              >
                Upload Files
                <svg 
                  width="20" 
                  height="20" 
                  viewBox="0 0 20 20" 
                  fill="none" 
                  xmlns="http://www.w3.org/2000/svg" 
                  className={`ml-2 transition-transform duration-200 ${showDropdown ? 'rotate-180' : ''}`}
                >
                  <path d="M5 7.5L10 12.5L15 7.5" stroke="#F7F2FA" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              
              {/* Dropdown Menu */}
              {showDropdown && (
                <div 
                  className="absolute right-0 mt-2 bg-white rounded-lg shadow-lg border border-gray-200 z-50"
                  style={{ width: 'max-content' }}
                >
                  <div className="py-2">
                    {uploadOptions.map((option) => (
                      <button 
                        key={option.id}
                        className="w-full text-left px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 flex items-center space-x-3"
                        onClick={() => navigateToUpload(option.id)}
                      >
                        <div className="flex-shrink-0">
                          <div className="w-5 h-5 text-gray-400">
                            {option.icon}
                          </div>
                        </div>
                        <div>
                          <div className="font-medium">{option.title}</div>
                          <div className="text-xs text-gray-500">{option.description}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Dynamic Content Area */}
      <div className="min-h-[400px]">
        {/* Empty State (No Files Uploaded) */}
        {!hasActiveRoute && !hasUploadedFiles && (
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="text-center">
              {/* Upload Empty Image */}
              <div className="mb-6">
                <img 
                  src={uploadEmptyImage} 
                  alt="Upload Empty State" 
                  className="mx-auto h-[180px] w-[180px] opacity-60"
                />
              </div>
              
              {/* Text Content */}
              <h2 
                style={{ 
                  color: 'var(--Foundation-Green-Normal, #033B4D)', 
                  fontFamily: 'var(--FontFamily, Comfortaa)', 
                  fontSize: 'var(--FontSize-H7_FontSize, 24px)', 
                  fontWeight: 700, 
                  lineHeight: 'var(--LineHeight-H7_LineHeight, 28px)' 
                }} 
                className="mb-2"
              >
                You don't have any uploaded files
              </h2>
              <p className="text-gray-500 mb-8">
                Upload your files and enjoy smooth integration<br />
                with our intuitive tools.
              </p>
              
              {/* Action Button */}
              <div className="flex items-center justify-center">
                <button 
                  className="btn btn-primary btn-lg"
                  onClick={() => navigateToUpload('single-csv')}
                >
                  <svg width="14" height="18" viewBox="0 0 14 18" fill="none" xmlns="http://www.w3.org/2000/svg" className="mr-2">
                    <path d="M1 9V10.908C1 13.3417 1 14.559 1.6645 15.3832C1.7987 15.5497 1.95032 15.7013 2.11675 15.8355C2.9425 16.5 4.15825 16.5 6.592 16.5C7.12075 16.5 7.3855 16.5 7.62775 16.4145C7.67775 16.3965 7.727 16.376 7.7755 16.353C8.008 16.242 8.19475 16.0553 8.569 15.681L12.121 12.129C12.5552 11.6955 12.7712 11.4788 12.886 11.2028C13 10.9268 13 10.6208 13 10.0073V7.5C13 4.67175 13 3.25725 12.121 2.379C11.242 1.50075 9.82825 1.5 7 1.5M7.75 16.125V15.75C7.75 13.629 7.75 12.5677 8.40925 11.9092C9.06775 11.25 10.129 11.25 12.25 11.25H12.625" stroke="#F7F2FA" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
                    <path d="M5.5 3.75C5.0575 3.29475 3.88 1.5 3.25 1.5C2.62 1.5 1.4425 3.29475 1 3.75M3.25 2.25V7.5" stroke="#F7F2FA" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                  Get Started with Single CSV
                </button>
              </div>
            </div>
          </div>
        )}
        
        {/* Uploaded Files View */}
        {!hasActiveRoute && hasUploadedFiles && (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-600">Total Files</p>
                    <p className="text-2xl font-semibold" style={{ color: 'var(--Foundation-Green-Normal, #033B4D)' }}>
                      {uploadedFiles.length}
                    </p>
                  </div>
                  <div className="p-2 bg-primary-50 rounded-lg">
                    <svg className="w-5 h-5 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                    </svg>
                  </div>
                </div>
              </div>
              
              <div className="bg-white rounded-lg border p-6">
                <div className="flex items-center">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-600">Completed</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {uploadedFiles.filter(f => f.status === 'completed').length}
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="bg-white rounded-lg border p-6">
                <div className="flex items-center">
                  <div className="p-2 bg-yellow-100 rounded-lg">
                    <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-600">Uploading</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {uploadedFiles.filter(f => f.status === 'uploading').length}
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="bg-white rounded-lg border p-6">
                <div className="flex items-center">
                  <div className="p-2 bg-red-100 rounded-lg">
                    <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-600">Errors</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {uploadedFiles.filter(f => f.status === 'error').length}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Batch Upload Groups */}
            {getBatchFiles().length > 0 && getBatchFiles().map(([batchName, batchFiles]) => (
              <div key={batchName} className="bg-white rounded-lg border overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 bg-green-50">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-medium text-gray-900">{batchName}</h3>
                      <p className="text-sm text-gray-600">
                        {formatBatchDate(batchFiles[0]?.selectedDate)} • 
                        {batchFiles.length} files • 
                        Uploaded {formatDate(batchFiles[0]?.uploadDate)}
                      </p>
                    </div>
                    <div className="flex items-center space-x-4">
                      <div className="text-sm text-gray-600">
                        <span className="text-green-600 font-medium">{getBatchStats(batchFiles).completed}</span> completed,
                        <span className="text-yellow-600 font-medium">{getBatchStats(batchFiles).uploading}</span> uploading,
                        <span className="text-red-600 font-medium">{getBatchStats(batchFiles).error}</span> errors
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Child Name (File)
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Size
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Status
                        </th>
                        <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {batchFiles.map((file) => (
                        <tr key={file.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center">
                              <svg className="w-5 h-5 text-Foundation-Green-Normal mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                              </svg>
                              <div>
                                <div className="text-sm font-medium text-gray-900">{file.name.replace('_Attendance.csv', '').replace('_', ' ')}</div>
                                <div className="text-xs text-gray-500">{file.name}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {formatFileSize(file.size)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusClass(file.status)}`}>
                              {formatStatus(file.status)}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                            <div className="flex items-center justify-end space-x-2">
                              <button onClick={() => downloadFile(file)} className="text-primary-500 hover:text-primary-700 p-1 rounded-full hover:bg-primary-50">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                              </button>
                              <button onClick={() => removeUploadedFile(file.id)} className="text-red-600 hover:text-red-900 p-1 rounded-full hover:bg-red-50">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}

            {/* Individual Files (Non-Batch) */}
            {getNonBatchFiles().length > 0 && (
              <div className="bg-white rounded-lg border overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                  <h3 className="text-lg font-medium text-gray-900">Individual Files</h3>
                  <p className="text-sm text-gray-500">Single uploads and scheduled files</p>
                </div>
                
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          File Name
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Type
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Size
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Upload Date
                        </th>
                        <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Status
                        </th>
                        <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {getNonBatchFiles().map((file) => (
                        <tr key={file.id} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center">
                              <svg className="w-5 h-5 text-gray-400 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              <div className="text-sm font-medium text-gray-900">{file.name}</div>
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getTypeClass(file.type)}`}>
                              {formatFileType(file.type)}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {formatFileSize(file.size)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {formatDate(file.uploadDate)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusClass(file.status)}`}>
                              {formatStatus(file.status)}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                            <div className="flex items-center justify-end space-x-2">
                              <button onClick={() => removeUploadedFile(file.id)} className="text-red-600 hover:text-red-800">
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                                </svg>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* Router View for Nested Upload Components */}
        {hasActiveRoute && <Outlet />}
      </div>
    </div>
  );
};

export default DataUploadView;
