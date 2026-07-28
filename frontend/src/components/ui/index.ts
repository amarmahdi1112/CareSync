// Badges
export { StatusBadge, AgeGroupBadge, ColorBadge } from './Badge';
export type { StatusVariant, AgeGroup } from './Badge';

// Empty & Error States
export { EmptyState, ErrorState, NoResults } from './EmptyState';

// Loading Skeletons
export { 
  Skeleton, 
  CardSkeleton, 
  ListSkeleton, 
  TableSkeleton,
  TableRowSkeleton,
  StatsCardSkeleton,
  StatsGridSkeleton,
  DetailPageSkeleton,
} from './Skeleton';

// Modals
export { Modal, ConfirmModal } from './Modal';

// Stats
export { StatsCard, StatsGrid } from './StatsCard';

// Headers
export { PageHeader, SimpleHeader } from './PageHeader';

// Search & Filters
export { 
  SearchInput, 
  SelectFilter, 
  ViewToggle, 
  SearchFilterBar,
} from './SearchFilter';

// Stepper
export { Stepper, VerticalStepper } from './Stepper';
export type { Step } from './Stepper';

// Error Boundary
export { default as ErrorBoundary } from './ErrorBoundary';

// Notifications (legacy - context-based)
export { 
  NotificationProvider, 
  NotificationContainer, 
  useNotifications,
} from './NotificationContainer';

// Toast (Zustand-based)
export { ToastContainer } from './Toast';
