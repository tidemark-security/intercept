import React, { useEffect, useRef, useState } from 'react';

import { IconButton } from '@/components/buttons/IconButton';

import { Check, Trash2, X } from 'lucide-react';
export interface LinkPopupProps {
  visible: boolean;
  initialUrl?: string;
  initialText?: string;
  onSubmit: (url: string, text?: string) => void;
  onCancel: () => void;
  onRemove?: () => void;
  position?: { x: number; y: number };
  anchorElement?: HTMLElement;
}

export const LinkPopup: React.FC<LinkPopupProps> = ({
  visible,
  initialUrl = '',
  initialText = '',
  onSubmit,
  onCancel,
  onRemove,
  position,
  anchorElement,
}) => {
  const [url, setUrl] = useState(initialUrl);
  const popupRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Update URL when initialUrl changes (e.g., editing existing link)
  useEffect(() => {
    setUrl(initialUrl);
  }, [initialUrl]);

  // Auto-focus input when popup opens
  useEffect(() => {
    if (visible && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [visible]);

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel();
      }
    };

    if (visible) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [visible, onCancel]);

  // Handle outside click to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        onCancel();
      }
    };

    if (visible) {
      // Use setTimeout to avoid closing immediately after opening
      const timer = setTimeout(() => {
        document.addEventListener('mousedown', handleClickOutside);
      }, 100);

      return () => {
        clearTimeout(timer);
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [visible, onCancel]);

  // Calculate popup position
  const getPopupStyle = (): React.CSSProperties => {
    if (position) {
      return {
        position: 'fixed',
        left: `${position.x}px`,
        top: `${position.y}px`,
        zIndex: 50,
      };
    }

    if (anchorElement) {
      const rect = anchorElement.getBoundingClientRect();
      return {
        position: 'fixed',
        left: `${rect.left}px`,
        top: `${rect.bottom + 8}px`,
        zIndex: 50,
      };
    }

    // Default: center of screen
    return {
      position: 'fixed',
      left: '50%',
      top: '50%',
      transform: 'translate(-50%, -50%)',
      zIndex: 50,
    };
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (url.trim()) {
      onSubmit(url.trim(), initialText);
      setUrl('');
    }
  };

  const handleRemove = () => {
    if (onRemove) {
      onRemove();
      setUrl('');
    }
  };

  if (!visible) {
    return null;
  }

  return (
    <div
      ref={popupRef}
      style={getPopupStyle()}
      className="bg-neutral-100 border border-neutral-300 rounded-md shadow-lg p-3 min-w-[320px]"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <input
          ref={inputRef}
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Enter URL (e.g., https://example.com)"
          className="w-full px-3 py-2 bg-neutral-50 text-neutral-900 border border-neutral-400 rounded text-sm focus:outline-none focus:border-brand-primary"
        />
        
        <div className="flex items-center gap-2 justify-end">
          {onRemove && initialUrl && (
            <IconButton
              icon={<Trash2 />}
              onClick={handleRemove}
              size="small"
              variant="destructive-primary"
            />
          )}
          <div className="flex-1" />
          <IconButton
            icon={<X />}
            onClick={onCancel}
            size="small"
            variant="neutral-secondary"
          />
          <IconButton
            icon={<Check />}
            onClick={() => handleSubmit()}
            size="small"
            variant="brand-primary"
            type="submit"
          />
        </div>
      </form>
    </div>
  );
};
