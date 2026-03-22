import React from 'react';
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from '@/components/buttons/Button';


import { AlertCircle, ArrowLeft, Home } from 'lucide-react';
interface NotFoundErrorProps {
  entityType: 'case' | 'task' | 'alert';
  entityId?: string | number | null;
  onBackToList?: () => void;
}

/**
 * Full-page 404 error component for when an entity is not found
 * 
 * Displays a user-friendly error message with options to:
 * - Go back to the list view
 * - Return to home
 * 
 * @param entityType - The type of entity that was not found (case, task, or alert)
 * @param entityId - The ID that was attempted to be accessed
 * @param onBackToList - Optional callback for back to list button
 */
export const NotFoundError: React.FC<NotFoundErrorProps> = ({
  entityType,
  entityId,
  onBackToList,
}) => {
  const navigate = useViewTransitionNavigate();

  const handleBackToList = () => {
    if (onBackToList) {
      onBackToList();
    } else {
      // Default navigation based on entity type
      switch (entityType) {
        case 'case':
          navigate('/cases');
          break;
        case 'task':
          navigate('/tasks');
          break;
        case 'alert':
          navigate('/alerts');
          break;
      }
    }
  };

  const handleGoHome = () => {
    navigate('/');
  };

  const entityLabel = entityType.charAt(0).toUpperCase() + entityType.slice(1);

  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="flex max-w-md flex-col items-center gap-6 px-8 py-12 text-center">
        <div className="flex h-24 w-24 items-center justify-center rounded-full bg-error-600/10">
          <AlertCircle className="text-[48px] text-error-500" />
        </div>
        
        <div className="flex flex-col gap-3">
          <h1 className="text-heading-2 font-heading-2 text-white">
            {entityLabel} Not Found
          </h1>
          <p className="text-body font-body text-subtext-color">
            {entityId ? (
              <>
                The {entityType} <span className="font-mono text-white">{entityId}</span> could not be found.<br /> 
                It may not exist or you may not have permission to view it.
              </>
            ) : (
              <>
                The {entityType} you're looking for could not be found.<br />
                It may not exist or you may not have permission to view it.
              </>
            )}
          </p>
        </div>

        <div className="flex w-full flex-col gap-3 sm:flex-row sm:justify-center">
          <Button
            variant="brand-secondary"
            size="large"
            icon={<ArrowLeft />}
            onClick={handleBackToList}
          >
            Back to {entityLabel}s
          </Button>
          <Button
            variant="neutral-secondary"
            size="large"
            icon={<Home />}
            onClick={handleGoHome}
          >
            Go Home
          </Button>
        </div>
      </div>
    </div>
  );
};
