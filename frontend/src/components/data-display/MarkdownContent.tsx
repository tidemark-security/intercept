import React from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';

import { cn } from '@/utils/cn';
import { useTheme } from '@/contexts/ThemeContext';
import { CodeBlock } from '@/components/data-display/CodeBlock';
import MermaidRenderer from '@/components/data-display/MermaidRenderer';
import { FullscreenViewer } from '@/components/overlays/FullscreenViewer';
import { useFullscreenViewer } from '@/hooks/useFullscreenViewer';
import { LinkBadge } from '@/components/data-display/LinkBadge';
const CODE_SNIPPET_LINES = 15;

interface ExpandableCodeBlockProps {
  language: string;
  code: string;
  resolvedTheme: 'dark' | 'light';
}

function ExpandableCodeBlock({ language, code, resolvedTheme }: ExpandableCodeBlockProps) {
  const viewer = useFullscreenViewer();
  const [isCopied, setIsCopied] = React.useState(false);
  const copyTimeoutRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        window.clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const totalLines = code.split('\n').length;
  const isTruncated = totalLines > CODE_SNIPPET_LINES;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      if (copyTimeoutRef.current !== null) {
        window.clearTimeout(copyTimeoutRef.current);
      }
      setIsCopied(true);
      copyTimeoutRef.current = window.setTimeout(() => {
        setIsCopied(false);
        copyTimeoutRef.current = null;
      }, 2000);
    } catch {
      console.error('Failed to copy code');
    }
  };

  if (!isTruncated) {
    return <CodeBlock language={language} code={code} resolvedTheme={resolvedTheme} />;
  }

  return (
    <>
      <button
        type="button"
        className="w-full overflow-hidden border border-neutral-border text-left transition hover:border-neutral-400"
        onClick={viewer.open}
      >
        <CodeBlock
          language={language}
          code={code}
          resolvedTheme={resolvedTheme}
          maxLines={CODE_SNIPPET_LINES}
          showLineNumbers
          className="pointer-events-none [&_button]:hidden [&_pre]:border-0 [&_pre]:!mb-0"
        />
        <div className="border-t border-neutral-border bg-neutral-100 px-3 py-1 text-center text-xs text-subtext-color">
          …{totalLines - CODE_SNIPPET_LINES} more lines — click to expand
        </div>
      </button>

      <FullscreenViewer
        open={viewer.isOpen}
        onOpenChange={viewer.setIsOpen}
        title={`Code — ${language}`}
        textMode
        copyAction={{
          label: 'Copy Code',
          icon: isCopied ? <Check /> : <Copy />,
          copied: isCopied,
          onAction: handleCopy,
        }}
      >
        <CodeBlock
          language={language}
          code={code}
          resolvedTheme={resolvedTheme}
          showLineNumbers
        />
      </FullscreenViewer>
    </>
  );
}

interface MarkdownContentProps {
  content: string;
  className?: string;
  isStreamingFromAi?: boolean;
  linkStyle?: 'badge' | 'inline';
}

const MarkdownContent: React.FC<MarkdownContentProps> = ({
  content,
  className,
  isStreamingFromAi = false,
  linkStyle = 'badge',
}) => {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  if (!content || content.trim() === '') {
    return null;
  }

  const sanitizeConfig = {
    tagNames: [
      'p', 'br', 'strong', 'em', 'u', 's', 'del',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li',
      'a', 'code', 'pre', 'blockquote', 'hr',
      'input', // Allow input for checkboxes
      'span', 'div', // Allow span and div for syntax highlighter
      'table', 'thead', 'tbody', 'tr', 'th', 'td' // Allow table elements (GFM tables)
    ],
    attributes: {
      a: ['href'],
      input: ['type', 'checked', 'disabled'], // Allow checkbox attributes
      li: ['className'], // Allow className for task list items
      code: ['className'], // Allow className for language specification
      pre: ['className', 'style'],
      span: ['className', 'style'], // Allow style for syntax highlighting
      div: ['className', 'style'],
      th: ['align'], // Allow text alignment on table headers
      td: ['align'], // Allow text alignment on table cells
      '*': ['className', 'style']
    },
    protocols: {
      href: ['http', 'https', 'mailto']
    }
  };

  return (
    <div className={cn("w-full min-w-0 [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown className="text-default-font w-full min-w-0 leading-[1.6] [overflow-wrap:anywhere]"
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeConfig]]}
        components={{
          h1: ({ children }) => <h1 className="text-[30px] leading-[36px] font-semibold mb-2 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h1>,
          h2: ({ children }) => <h2 className="text-[20px] leading-[24px] font-semibold mb-2 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h2>,
          h3: ({ children }) => <h3 className="text-[16px] leading-[20px] font-semibold mb-2 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h3>,
          h4: ({ children }) => <h4 className="text-[14px] leading-[20px] font-semibold mb-2 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h4>,
          h5: ({ children }) => <h5 className="text-sm font-semibold mb-1 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h5>,
          h6: ({ children }) => <h6 className="text-sm font-medium mb-1 mt-2 first:mt-0 text-default-font" style={{ fontFamily: '"Saira Condensed", sans-serif' }}>{children}</h6>,
          p: ({ children }) => <p className="text-sm leading-[1.6] my-3 first:mt-0 last:mb-0 [overflow-wrap:anywhere]">{children}</p>,
          ul: ({ children, className: ulClassName }) => {
            // Check if this is a task list (GFM checkbox list)
            const isTaskList = ulClassName?.includes('contains-task-list');
            return (
              <ul className={`mb-2 mt-2 space-y-0 text-sm leading-[1.6] [overflow-wrap:anywhere] ${isTaskList ? 'list-none pl-0' : 'list-disc pl-6'}`}>
                {children}
              </ul>
            );
          },
          ol: ({ children }) => <ol className="list-decimal pl-6 mb-2 mt-2 space-y-0 text-sm leading-[1.6] [overflow-wrap:anywhere]">{children}</ol>,
          li: ({ children, className: liClassName }) => {
            // Check if this is a task list item
            const isTaskItem = liClassName?.includes('task-list-item');

            if (isTaskItem) {
              // Check if the task is completed by looking for a checked checkbox in children
              const isCompleted = React.Children.toArray(children).some(
                (child: any) => child?.props?.type === 'checkbox' && child?.props?.checked
              );

              return (
                <li className="flex items-start gap-2 my-0 leading-[1.6] [overflow-wrap:anywhere]" style={{ listStyle: 'none' }}>
                  <span className={isCompleted ? 'line-through flex items-start gap-2' : 'flex items-start gap-2'}>
                    {children}
                  </span>
                </li>
              );
            }

            return <li className="my-0 leading-[1.6] [overflow-wrap:anywhere]">{children}</li>;
          },
          input: ({ type, checked, disabled }) => {
            // Render checkboxes for task lists to match MDXEditor style
            if (type === 'checkbox') {
              return (
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={disabled}
                  className="mt-[3px] flex-shrink-0 w-4 h-4 cursor-default appearance-none border border-neutral-500 rounded bg-transparent checked:bg-brand-primary checked:border-brand-primary relative
                    before:content-[''] before:absolute before:left-[4px] before:top-[1px] before:w-[5px] before:h-[9px] before:border-r-2 before:border-b-2 before:border-black before:rotate-45 before:opacity-0 checked:before:opacity-100"
                  readOnly
                />
              );
            }
            return null;
          },
          blockquote: ({ children }) => (
            <blockquote className="border-l-[3px] border-brand-500 pl-4 my-4 text-default-font leading-[1.6] [overflow-wrap:anywhere]">
              {children}
            </blockquote>
          ),
          code: (props: any) => {
            const { node, inline, className, children, ...rest } = props;
            const match = /language-(\w+)/.exec(className || '');

            // Check if this is inline code (not in a pre block)
            const isInline = inline !== false && !className;

            if (isInline) {
              return (
                <code
                  className={cn(
                    'text-brand-300 font-mono px-[6px] py-[2px] rounded text-sm',
                    isDarkTheme ? 'bg-neutral-200' : 'bg-neutral-600'
                  )}
                  {...rest}
                >
                  {children}
                </code>
              );
            }

            // Block code with syntax highlighting
            const language = match ? match[1] : 'text';
            const codeString = String(children).replace(/\n$/, '');

            if (language === 'mermaid') {
              return <MermaidRenderer code={codeString} isStreaming={isStreamingFromAi} />;
            }

            return <ExpandableCodeBlock language={language} code={codeString} resolvedTheme={resolvedTheme} />;
          },
          a: ({ href, children }) => {
            if (linkStyle === 'inline') {
              return (
                <a
                  href={href || '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={cn(
                    'underline underline-offset-2',
                    isDarkTheme ? 'text-brand-primary hover:text-brand-400' : 'text-brand-700 hover:text-brand-800'
                  )}
                >
                  {children}
                </a>
              );
            }

            return (
              <LinkBadge href={href || '#'}>
                {children}
              </LinkBadge>
            );
          },
          hr: () => <hr className="border-neutral-300 my-4" />,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          del: ({ children }) => <del className="line-through">{children}</del>,
          u: ({ children }) => <u>{children}</u>,
          s: ({ children }) => <s className="line-through">{children}</s>,
          table: ({ children }) => (
            <div className="overflow-x-auto my-4 w-full min-w-0">
              <table className="min-w-full border-collapse border border-neutral-border text-sm">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-neutral-100">{children}</thead>,
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <tr className="border-b border-neutral-border">{children}</tr>,
          th: ({ children, style }) => (
            <th className="px-3 py-2 text-left font-semibold leading-[1.6] text-default-font border border-neutral-border" style={style}>
              {children}
            </th>
          ),
          td: ({ children, style }) => (
            <td className="px-3 py-2 text-default-font leading-[1.6] border border-neutral-border [overflow-wrap:anywhere]" style={style}>
              {children}
            </td>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default React.memo(MarkdownContent, (prevProps, nextProps) => {
  return (
    prevProps.content === nextProps.content &&
    prevProps.className === nextProps.className &&
    prevProps.isStreamingFromAi === nextProps.isStreamingFromAi
  );
});