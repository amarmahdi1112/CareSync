import React from 'react';
import { CheckIcon } from '@heroicons/react/24/solid';

export interface Step {
  id: string;
  title: string;
  description?: string;
}

interface StepperProps {
  steps: Step[];
  currentStep: number;
  onStepClick?: (stepIndex: number) => void;
}

export const Stepper: React.FC<StepperProps> = ({ steps, currentStep, onStepClick }) => {
  return (
    <nav aria-label="Progress" className="w-full">
      <ol className="flex items-center justify-between">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const isClickable = onStepClick && index < currentStep;
          const isLast = index === steps.length - 1;

          return (
            <li key={step.id} className={`relative flex items-center ${!isLast ? 'flex-1' : ''}`}>
              <div
                className={`group flex flex-col items-center ${isClickable ? 'cursor-pointer' : ''}`}
                onClick={() => isClickable && onStepClick(index)}
              >
                {/* Step circle */}
                <span
                  className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all duration-200 ${
                    isCompleted
                      ? 'bg-primary-600 border-primary-600 group-hover:bg-primary-700'
                      : isCurrent
                      ? 'border-primary-600 bg-white shadow-sm'
                      : 'border-gray-300 bg-white'
                  }`}
                >
                  {isCompleted ? (
                    <CheckIcon className="h-4 w-4 text-white" />
                  ) : (
                    <span
                      className={`text-xs font-semibold ${
                        isCurrent ? 'text-primary-600' : 'text-gray-400'
                      }`}
                    >
                      {index + 1}
                    </span>
                  )}
                </span>

                {/* Step text */}
                <span
                  className={`mt-2 text-xs font-medium text-center whitespace-nowrap ${
                    isCompleted || isCurrent ? 'text-primary-600' : 'text-gray-400'
                  }`}
                >
                  {step.title}
                </span>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div className="flex-1 mx-2 h-0.5 bg-gray-200 self-start mt-4">
                  <div
                    className={`h-full transition-all duration-300 ${isCompleted ? 'bg-primary-600' : 'bg-transparent'}`}
                    style={{ width: isCompleted ? '100%' : '0%' }}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

// Mobile-friendly vertical stepper
export const VerticalStepper: React.FC<StepperProps> = ({ steps, currentStep }) => {
  return (
    <nav aria-label="Progress">
      <ol className="space-y-4">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;

          return (
            <li key={step.id} className="relative flex gap-4">
              {/* Connector line */}
              {index !== steps.length - 1 && (
                <div
                  className={`absolute left-4 top-8 -ml-px h-full w-0.5 ${
                    isCompleted ? 'bg-primary-600' : 'bg-gray-200'
                  }`}
                />
              )}

              {/* Step circle */}
              <div
                className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                  isCompleted
                    ? 'bg-primary-600'
                    : isCurrent
                    ? 'border-2 border-primary-600 bg-white'
                    : 'border-2 border-gray-300 bg-white'
                }`}
              >
                {isCompleted ? (
                  <CheckIcon className="h-5 w-5 text-white" />
                ) : (
                  <span className={`text-sm font-medium ${isCurrent ? 'text-primary-600' : 'text-gray-500'}`}>
                    {index + 1}
                  </span>
                )}
              </div>

              {/* Step text */}
              <div className="pt-1">
                <p className={`text-sm font-medium ${isCompleted || isCurrent ? 'text-primary-600' : 'text-gray-500'}`}>
                  {step.title}
                </p>
                {step.description && (
                  <p className="text-xs text-gray-500">{step.description}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

export default Stepper;
