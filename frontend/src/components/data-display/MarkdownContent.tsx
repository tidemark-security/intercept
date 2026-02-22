import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import rehypeSanitize from 'rehype-sanitize';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { cn } from '@/utils/cn';
import { useTheme } from '@/contexts/ThemeContext';

import { Check, Copy } from 'lucide-react';
import { LinkBadge } from '@/components/data-display/LinkBadge';
interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * CodeBlock component with syntax highlighting and copy-to-clipboard functionality
 */
interface CodeBlockProps {
  language: string;
  code: string;
}

interface CodeBlockThemeProps extends CodeBlockProps {
  resolvedTheme: "dark" | "light";
}

const CodeBlock: React.FC<CodeBlockThemeProps> = ({ language, code, resolvedTheme }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

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
      className="relative"
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
        style={resolvedTheme === "dark" ? vscDarkPlus : oneLight}
        className="w-full min-w-0 max-w-full rounded-sm overflow-x-auto border border-neutral-border !mt-0"
        showLineNumbers
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
        {code}
      </SyntaxHighlighter>
    </div>
  );
};

const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className }) => {
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

            return <CodeBlock language={language} code={codeString} resolvedTheme={resolvedTheme} />;
          },
          a: ({ href, children }) => (
            <LinkBadge href={href || '#'}>
              {children}
            </LinkBadge>
          ),
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

export default MarkdownContent;