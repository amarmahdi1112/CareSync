// ============================================
// Modal Components
// ============================================

import React from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

// -------------------- Base Modal --------------------

interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  disableClose?: boolean;
}

export const BaseModal: React.FC<BaseModalProps> = ({
  isOpen,
  onClose,
  children,
  maxWidth = 'lg',
  disableClose = false,
}) => {
  if (!isOpen) return null;

  const maxWidthClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="fixed inset-0 bg-black bg-opacity-25"
          onClick={disableClose ? undefined : onClose}
        />
        <div className={`relative bg-white rounded-2xl shadow-xl w-full ${maxWidthClasses[maxWidth]} max-h-[90vh] overflow-y-auto`}>
          {children}
        </div>
      </div>
    </div>
  );
};

// -------------------- Modal Header --------------------

interface ModalHeaderProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  iconBg?: string;
  onClose?: () => void;
  showClose?: boolean;
}

export const ModalHeader: React.FC<ModalHeaderProps> = ({
  title,
  subtitle,
  icon,
  iconBg = 'bg-primary-100',
  onClose,
  showClose = true,
}) => {
  return (
    <div className="flex items-center justify-between p-6 border-b border-gray-200 sticky top-0 bg-white">
      <div className="flex items-center gap-3">
        {icon && (
          <div className={`p-2 ${iconBg} rounded-lg`}>
            {icon}
          </div>
        )}
        <div>
          <h2 className="text-xl font-bold text-gray-900">{title}</h2>
          {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
        </div>
      </div>
      {showClose && onClose && (
        <button
          onClick={onClose}
          className="p-2 text-gray-400 hover:text-gray-600 rounded-lg"
        >
          <XMarkIcon className="h-6 w-6" />
        </button>
      )}
    </div>
  );
};

// -------------------- Modal Body --------------------

interface ModalBodyProps {
  children: React.ReactNode;
  className?: string;
}

export const ModalBody: React.FC<ModalBodyProps> = ({ children, className = '' }) => {
  return <div className={`p-6 space-y-6 ${className}`}>{children}</div>;
};

// -------------------- Modal Footer --------------------

interface ModalFooterProps {
  children: React.ReactNode;
}

export const ModalFooter: React.FC<ModalFooterProps> = ({ children }) => {
  return (
    <div className="p-6 border-t border-gray-200 flex justify-end gap-3 sticky bottom-0 bg-white">
      {children}
    </div>
  );
};

// -------------------- Composed Modal --------------------

interface ComposedModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  iconBg?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  disableClose?: boolean;
}

export const Modal: React.FC<ComposedModalProps> = ({
  isOpen,
  onClose,
  title,
  subtitle,
  icon,
  iconBg,
  children,
  footer,
  maxWidth = 'lg',
  disableClose = false,
}) => {
  return (
    <BaseModal isOpen={isOpen} onClose={onClose} maxWidth={maxWidth} disableClose={disableClose}>
      <ModalHeader
        title={title}
        subtitle={subtitle}
        icon={icon}
        iconBg={iconBg}
        onClose={disableClose ? undefined : onClose}
        showClose={!disableClose}
      />
      <ModalBody>{children}</ModalBody>
      {footer && <ModalFooter>{footer}</ModalFooter>}
    </BaseModal>
  );
};

// -------------------- Button Components for Modals --------------------

interface ModalButtonProps {
  onClick: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
  children: React.ReactNode;
  className?: string;
}

export const ModalButton: React.FC<ModalButtonProps> = ({
  onClick,
  disabled = false,
  variant = 'primary',
  loading = false,
  children,
  className = '',
}) => {
  const variants = {
    primary: 'bg-primary-600 text-white hover:bg-primary-700',
    secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200',
    danger: 'bg-red-600 text-white hover:bg-red-700',
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`px-4 py-2 font-medium rounded-lg disabled:opacity-50 ${variants[variant]} ${className}`}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          Loading...
        </span>
      ) : (
        children
      )}
    </button>
  );
};

// -------------------- Alert Banner --------------------

interface AlertBannerProps {
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

export const AlertBanner: React.FC<AlertBannerProps> = ({ type, message }) => {
  const styles = {
    success: 'bg-green-50 text-green-700',
    error: 'bg-red-50 text-red-700',
    info: 'bg-blue-50 text-blue-700',
    warning: 'bg-yellow-50 text-yellow-700',
  };

  return (
    <div className={`p-4 rounded-lg ${styles[type]}`}>
      {message}
    </div>
  );
};
