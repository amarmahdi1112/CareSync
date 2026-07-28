import React from 'react';

interface StepHeaderProps {
  icon: React.ReactNode;
  iconBgColor: string;
  title: string;
  subtitle: string;
}

export const StepHeader: React.FC<StepHeaderProps> = ({ 
  icon, 
  iconBgColor, 
  title, 
  subtitle 
}) => (
  <div className="text-center">
    <div className={`mx-auto w-14 h-14 ${iconBgColor} rounded-full flex items-center justify-center mb-4`}>
      {icon}
    </div>
    <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
    <p className="text-gray-500 mt-1">{subtitle}</p>
  </div>
);
