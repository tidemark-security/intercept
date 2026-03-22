import React from 'react';

export function useFullscreenViewer(initialOpen = false) {
  const [isOpen, setIsOpen] = React.useState(initialOpen);

  const open = React.useCallback(() => {
    setIsOpen(true);
  }, []);

  const close = React.useCallback(() => {
    setIsOpen(false);
  }, []);

  return {
    isOpen,
    open,
    close,
    setIsOpen,
  };
}