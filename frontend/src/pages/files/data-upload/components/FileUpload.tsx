import React, { useState, useRef } from 'react';
import type { ReactNode } from 'react';

interface FileUploadProps {
  acceptedTypes?: string[];
  maxSize?: number;
  multiple?: boolean;
  title?: string;
  description?: string;
  headerLabel?: string;
  headerIcon?: ReactNode;
  uploadIcon?: ReactNode;
  buttonIcon?: ReactNode;
  fileIcon?: ReactNode;
  removeIcon?: ReactNode;
  errorIcon?: ReactNode;
  onFileSelected?: (files: File[]) => void;
  onUploadStart?: () => void;
  onUploadComplete?: () => void;
  onUploadError?: (error: string) => void;
}

const FileUpload: React.FC<FileUploadProps> = ({
  acceptedTypes = ['csv'],
  maxSize = 52428800, // 50MB
  multiple = false,
  title = 'Upload your CSV file',
  description = 'Drag and drop your file here, or click to browse',
  headerLabel = 'Upload File',
  headerIcon,
  uploadIcon,
  buttonIcon,
  fileIcon,
  removeIcon,
  errorIcon,
  onFileSelected,
  // onUploadStart - available but not used yet
  // onUploadComplete - available but not used yet
  onUploadError
}) => {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [fileProgress, setFileProgress] = useState<Record<number, number>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const maxSizeDisplay = formatFileSize(maxSize);
  const acceptAttribute = acceptedTypes.map(type => `.${type}`).join(',');

  function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  const validateFile = (file: File): string | null => {
    const fileExtension = file.name.split('.').pop()?.toLowerCase();
    if (fileExtension && !acceptedTypes.includes(fileExtension)) {
      return `File type .${fileExtension} is not supported. Please upload: ${acceptedTypes.join(', ')}`;
    }
    if (file.size > maxSize) {
      return `File size (${formatFileSize(file.size)}) exceeds maximum allowed size (${maxSizeDisplay})`;
    }
    return null;
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    processFiles(files);
  };

  const processFiles = (files: File[]) => {
    setErrorMessage('');
    const validFiles: File[] = [];
    
    for (const file of files) {
      const error = validateFile(file);
      if (error) {
        setErrorMessage(error);
        onUploadError?.(error);
        return;
      }
      validFiles.push(file);
    }

    if (!multiple && validFiles.length > 1) {
      setErrorMessage('Please select only one file');
      return;
    }

    setSelectedFiles(multiple ? [...selectedFiles, ...validFiles] : validFiles);
    onFileSelected?.(validFiles);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragOver(false);
    const files = Array.from(event.dataTransfer.files);
    processFiles(files);
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
  };

  const handleDragEnter = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    setIsDragOver(false);
  };

  const openFileDialog = () => {
    fileInputRef.current?.click();
  };

  const removeFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(newFiles);
    const newProgress = { ...fileProgress };
    delete newProgress[index];
    setFileProgress(newProgress);
  };

  return (
    <div className="w-full">
      {/* Header with Icon and Label */}
      {(headerLabel || headerIcon) && (
        <div className="flex items-center space-x-2 mb-6">
          {headerIcon && (
            <div className="flex-shrink-0">
              {headerIcon}
            </div>
          )}
          <span 
            className="text-base font-medium"
            style={{ color: 'var(--Foundation-Green-Normal, #033B4D)' }}
          >
            {headerLabel}
          </span>
        </div>
      )}

      {/* File Upload Area */}
      <div 
        className={`relative border-2 border-dashed rounded-xl bg-white transition-all duration-200 h-80 ${
          isDragOver 
            ? 'border-purple-400 bg-purple-50' 
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
      >
        {/* Upload Area (shown when no files selected) */}
        {selectedFiles.length === 0 ? (
          <div className="h-full flex items-center justify-center p-8 text-center">
            <div className="mb-8">
              {/* Upload Icon */}
              <div className="h-12 w-12 mx-auto mb-4 opacity-50 flex items-center justify-center">
                {uploadIcon}
              </div>
              <div className="space-y-6">
                <div className="space-y-2">
                  <h3 
                    style={{ 
                      color: 'var(--Foundation-Green-Normal, #033B4D)', 
                      fontFamily: 'var(--FontFamily, Comfortaa)', 
                      fontSize: 'var(--FontSize-H7_FontSize, 24px)', 
                      fontWeight: 700, 
                      lineHeight: 'var(--LineHeight-H7_LineHeight, 28px)' 
                    }}
                  >
                    {title}
                  </h3>
                  <p className="text-gray-600 text-base">
                    {description}
                  </p>
                </div>
                {/* File Info */}
                <p className="text-sm text-gray-500">
                  Max File Size: {maxSizeDisplay}
                </p>
              </div>
              
              {/* Upload Button */}
              <button 
                className="btn btn-primary mt-4"
                onClick={openFileDialog}
              >
                {buttonIcon && <span className="mr-2">{buttonIcon}</span>}
                Browse Files
              </button>
            </div>
          </div>
        ) : (
          /* Selected Files List (shown when files are selected) */
          <div className="h-full flex flex-col p-6">
            <div className="flex-1 overflow-y-auto space-y-2 max-h-full">
              {selectedFiles.map((file, index) => (
                <div 
                  key={index}
                  className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg flex-shrink-0 border-b border-gray-100"
                >
                  <div className="flex items-center space-x-3 flex-1">
                    <div className="flex-shrink-0">
                      {fileIcon || (
                        <svg 
                          className="w-5 h-5" 
                          style={{ color: 'var(--Foundation-Green-Normal, #033B4D)' }} 
                          fill="none" 
                          stroke="currentColor" 
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                        </svg>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <p 
                          className="text-sm font-medium truncate" 
                          style={{ color: 'var(--Foundation-Green-Normal, #033B4D)' }}
                        >
                          {file.name}
                        </p>
                        <p className="text-sm text-gray-500 ml-2">{formatFileSize(file.size)}</p>
                      </div>
                      {/* Progress bar for individual file */}
                      {fileProgress[index] && fileProgress[index] > 0 && fileProgress[index] < 100 && (
                        <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                          <div 
                            className="bg-teal-500 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${fileProgress[index]}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                  <button 
                    onClick={() => removeFile(index)}
                    className="ml-4 flex-shrink-0 p-2 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-full transition-colors"
                    title="Delete File"
                  >
                    {removeIcon || (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                      </svg>
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Hidden File Input */}
        <input
          ref={fileInputRef}
          type="file"
          accept={acceptAttribute}
          multiple={multiple}
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {/* Error Messages */}
      {errorMessage && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl">
          <div className="flex items-center space-x-2">
            {errorIcon}
            <p className="text-sm font-medium text-red-700">{errorMessage}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default FileUpload;
