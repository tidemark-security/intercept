import React, { useState } from 'react';
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Check, Copy } from 'lucide-react';

import { cn } from '@/utils/cn';

export interface CodeBlockProps {
  language: string;
  code: string;
  resolvedTheme: 'dark' | 'light';
  maxLines?: number;
  showLineNumbers?: boolean;
  className?: string;
  /** When true and maxLines is set, show a "click to expand" footer that toggles inline. */
  collapsible?: boolean;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  language,
  code,
  resolvedTheme,
  maxLines,
  showLineNumbers = true,
  className,
  collapsible = false,
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const totalLines = code.split('\n').length;
  const isTruncated = Boolean(maxLines && totalLines > maxLines);
  const showTruncated = isTruncated && collapsible && !isExpanded;

  const displayCode = maxLines && !isExpanded
    ? code.split('\n').slice(0, maxLines).join('\n')
    : code;

  const handleCopy = () => {
    navigator.clipboard.writeText(code)
      .then(() => {
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
      })
      .catch(err => {
        console.error('Failed to copy code:', err);
      });
  };

  return (
    <div
      className={cn('relative', className)}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Copy button */}
      <button
        onClick={handleCopy}
        className={cn(
          "absolute top-2 right-2 p-1.5 rounded bg-neutral-100 hover:bg-neutral-200 transition-all z-10",
          { "opacity-0": !isHovered && !isCopied, "opacity-100": isHovered || isCopied }
        )}
        title="Copy to clipboard"
      >
        {isCopied ? (
          <Check className="h-4 w-4 text-success-600" />
        ) : (
          <Copy className="h-4 w-4 text-neutral-400" />
        )}
      </button>
      
      <SyntaxHighlighter
        language={language}
        style={resolvedTheme === "dark" ? oneDark : oneLight}
        className="w-full min-w-0 max-w-full overflow-x-auto border border-neutral-border !mt-0"
        customStyle={{ borderRadius: 0 }}
        showLineNumbers={showLineNumbers}
        wrapLongLines
        lineProps={{
          style: {
            display: 'flex',
            flexWrap: 'wrap',
          }
        }}
        codeTagProps={{
          style: {
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            overflowWrap: 'anywhere',
          }
        }}
      >
        {displayCode}
      </SyntaxHighlighter>

      {showTruncated && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded(true);
          }}
          className="w-full border-t border-neutral-border bg-neutral-100 px-3 py-1 text-center text-xs text-subtext-color hover:bg-neutral-200 transition-colors"
        >
          …{totalLines - maxLines!} more lines — click to expand
        </button>
      )}
      {collapsible && isExpanded && isTruncated && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded(false);
          }}
          className="w-full border-t border-neutral-border bg-neutral-100 px-3 py-1 text-center text-xs text-subtext-color hover:bg-neutral-200 transition-colors"
        >
          collapse
        </button>
      )}
    </div>
  );
};
