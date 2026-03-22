

"use client";

import React, { useRef, useState } from "react";
import {
  MDXEditor,
  MDXEditorMethods,
  RemoteMDXEditorRealmProvider,
  useRemoteMDXEditorRealm,
  headingsPlugin,
  listsPlugin,
  quotePlugin,
  linkPlugin,
  tablePlugin,
  codeBlockPlugin,
  codeMirrorPlugin,
  CodeMirrorEditor,
  thematicBreakPlugin,
  markdownShortcutPlugin,
  remoteRealmPlugin,
  diffSourcePlugin,
  viewMode$,
  applyFormat$,
  applyListType$,
  updateLink$,
  removeLink$,
  convertSelectionToNode$,
  activeEditor$,
} from "@mdxeditor/editor";
import { $createParagraphNode, $getSelection, $isRangeSelection } from "lexical";
import { $createHeadingNode, $createQuoteNode } from "@lexical/rich-text";
import { $createLinkNode, TOGGLE_LINK_COMMAND, $isLinkNode } from "@lexical/link";
import "@mdxeditor/editor/style.css";
import "@/styles/mdxeditor-dark.css";

















import { cn } from "@/utils/cn";
import { IconButton } from "@/components/buttons/IconButton";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { LinkPopup } from "@/components/overlays/LinkPopup";
import { useTheme } from "@/contexts/ThemeContext";

import { Bold, Code2, Eye, FileText, Heading, Heading1, Heading2, Heading3, Heading4, Italic, Link, List, ListChecks, ListOrdered, MessageSquare, Strikethrough, Type } from 'lucide-react';
interface MarkdownInputRootProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'> {
  variant?: "default" | "compact";
  className?: string;
  value?: string;
  onChange?: (value?: string) => void;
  autoFocus?: boolean;
}

// Internal component that handles toolbar interactions with the editor
interface ToolbarControllerProps {
  editorId: string;
}

const ToolbarController: React.FC<ToolbarControllerProps> = ({
  editorId,
}) => {
  const realm = useRemoteMDXEditorRealm(editorId);

  React.useEffect(() => {
    if (realm) {
      // Setup handlers that will be called from toolbar buttons
      (window as any)[`mdxToolbar_${editorId}`] = {
        toggleBold: () => realm.pub(applyFormat$, 'bold'),
        toggleItalic: () => realm.pub(applyFormat$, 'italic'),
        toggleStrikethrough: () => realm.pub(applyFormat$, 'strikethrough'),
        insertInlineCode: () => realm.pub(applyFormat$, 'code'),
        toggleBulletList: () => realm.pub(applyListType$, 'bullet'),
        toggleCheckList: () => realm.pub(applyListType$, 'check'),
        toggleOrderedList: () => realm.pub(applyListType$, 'number'),
        setViewMode: (mode: 'rich-text' | 'source' | 'diff') => realm.pub(viewMode$, mode),
        setBlockType: (type: string) => {
          // Workaround for applyBlockType$ bug: https://github.com/mdx-editor/editor/issues/667
          // Use convertSelectionToNode$ instead (same as official BlockTypeSelect component)
          switch (type) {
            case 'paragraph':
              realm.pub(convertSelectionToNode$, () => $createParagraphNode());
              break;
            case 'quote':
              realm.pub(convertSelectionToNode$, () => $createQuoteNode());
              break;
            default:
              // Handle all heading types (h1-h6)
              if (type.startsWith('h')) {
                realm.pub(convertSelectionToNode$, () => $createHeadingNode(type as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'));
              }
          }
        },
        insertLink: (url: string) => {
          const editor = realm.getValue(activeEditor$);
          if (editor) {
            editor.dispatchCommand(TOGGLE_LINK_COMMAND, url);
          }
        },
        getLinkAtCursor: () => {
          const editor = realm.getValue(activeEditor$);
          if (!editor) return null;
          
          let linkUrl: string | null = null;
          editor.getEditorState().read(() => {
            const selection = $getSelection();
            if ($isRangeSelection(selection)) {
              const node = selection.anchor.getNode();
              const parent = node.getParent();
              
              // Check if the node itself is a link or if its parent is
              if ($isLinkNode(node)) {
                linkUrl = node.getURL();
              } else if ($isLinkNode(parent)) {
                linkUrl = parent.getURL();
              }
            }
          });
          return linkUrl;
        },
        updateLink: (url: string, title?: string) => realm.pub(updateLink$, { url, title: title || url }),
        removeLink: () => realm.pub(removeLink$, undefined),
      };
    }
    return () => {
      delete (window as any)[`mdxToolbar_${editorId}`];
    };
  }, [realm, editorId]);

  return null;
};

const MarkdownInputRoot = React.forwardRef<
  HTMLDivElement,
  MarkdownInputRootProps
>(function MarkdownInputRoot(
  { variant = "default", className, value, onChange, autoFocus = false, ...otherProps }: MarkdownInputRootProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const mdxEditorRef = useRef<MDXEditorMethods>(null);
  const editorIdRef = useRef(`markdown-editor-${Math.random().toString(36).substring(7)}`);
  const editorId = editorIdRef.current;
  
  const headingButtonRef = useRef<HTMLButtonElement>(null);
  const linkButtonRef = useRef<HTMLDivElement>(null);
  const [currentViewMode, setCurrentViewMode] = useState<'rich-text' | 'source'>('rich-text');
  const [linkPopupVisible, setLinkPopupVisible] = useState(false);
  const [linkData, setLinkData] = useState<{ url: string; text: string } | null>(null);

  // Toolbar button handlers that call into the realm via window object
  const handleToggleBold = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleBold();
    mdxEditorRef.current?.focus();
  };

  const handleToggleItalic = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleItalic();
    mdxEditorRef.current?.focus();
  };

  const handleToggleStrikethrough = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleStrikethrough();
    mdxEditorRef.current?.focus();
  };

  const handleInsertInlineCode = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.insertInlineCode();
    mdxEditorRef.current?.focus();
  };

  const handleToggleBulletList = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleBulletList();
    mdxEditorRef.current?.focus();
  };

  const handleToggleCheckList = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleCheckList();
    mdxEditorRef.current?.focus();
  };

  const handleToggleOrderedList = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.toggleOrderedList();
    mdxEditorRef.current?.focus();
  };

  const handleSetBlockType = (type: string) => {
    // Focus editor FIRST, then apply block type
    if (mdxEditorRef.current) {
      mdxEditorRef.current.focus();
    }
    (window as any)[`mdxToolbar_${editorId}`]?.setBlockType(type);
  };

  const handleLinkClick = () => {
    // Check if there's already a link at the cursor position
    const existingUrl = (window as any)[`mdxToolbar_${editorId}`]?.getLinkAtCursor();
    
    // Show our custom popup with existing URL if present
    setLinkData({ 
      url: existingUrl || '', 
      text: '' 
    });
    setLinkPopupVisible(true);
  };

  const handleLinkSubmit = (url: string, text?: string) => {
    // Insert or update the link in the editor
    (window as any)[`mdxToolbar_${editorId}`]?.insertLink(url);
    setLinkPopupVisible(false);
    setLinkData(null);
    mdxEditorRef.current?.focus();
  };

  const handleLinkCancel = () => {
    setLinkPopupVisible(false);
    setLinkData(null);
    mdxEditorRef.current?.focus();
  };

  const handleLinkRemove = () => {
    (window as any)[`mdxToolbar_${editorId}`]?.removeLink();
    setLinkPopupVisible(false);
    setLinkData(null);
    mdxEditorRef.current?.focus();
  };

  const handleViewModeToggle = (mode: 'rich-text' | 'source') => {
    (window as any)[`mdxToolbar_${editorId}`]?.setViewMode(mode);
    setCurrentViewMode(mode);
  };

  return (
    <RemoteMDXEditorRealmProvider>
      <ToolbarController editorId={editorId} />
      <div
        className={cn(
          "group/6750cb22 flex w-full flex-col items-start gap-4 rounded-md min-h-0",
          { "flex-col flex-nowrap gap-1": variant === "compact" },
          className
        )}
        ref={ref}
        {...otherProps}
      >
      <div className="flex w-full flex-none items-center gap-1">
        <IconButton 
          size="small" 
          icon={<Bold />} 
          onClick={handleToggleBold}
        />
        <IconButton 
          size="small" 
          icon={<Italic />} 
          onClick={handleToggleItalic}
        />
        <IconButton 
          size="small" 
          icon={<Strikethrough />} 
          onClick={handleToggleStrikethrough}
        />
        <div className="flex w-px flex-none flex-col items-center gap-2 self-stretch bg-neutral-border" />
        
        {/* Font/Style Dropdown */}
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              ref={headingButtonRef}
              className="group/af9405b1 flex h-8 w-8 cursor-pointer flex-col items-center justify-center gap-2 rounded-md bg-transparent hover:bg-neutral-100 active:bg-neutral-100"
            >
              <Heading className="text-body font-body text-neutral-700" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content
            side="bottom"
            align="start"
            sideOffset={4}
          >
                <DropdownMenu.DropdownItem
                  icon={<Type />}
                  label="Paragraph"
                  onClick={() => handleSetBlockType('paragraph')}
                />
                <DropdownMenu.DropdownItem
                  icon={<MessageSquare />}
                  label="Quote"
                  onClick={() => handleSetBlockType('quote')}
                />
                <DropdownMenu.DropdownDivider />
                <DropdownMenu.DropdownItem
                  icon={<Heading1 />}
                  label="Heading 1"
                  onClick={() => handleSetBlockType('h1')}
                />
                <DropdownMenu.DropdownItem
                  icon={<Heading2 />}
                  label="Heading 2"
                  onClick={() => handleSetBlockType('h2')}
                />
                <DropdownMenu.DropdownItem
                  icon={<Heading3 />}
                  label="Heading 3"
                  onClick={() => handleSetBlockType('h3')}
                />
                <DropdownMenu.DropdownItem
                  icon={<Heading4 />}
                  label="Heading 4"
                  onClick={() => handleSetBlockType('h4')}
                />
          </DropdownMenu.Content>
        </DropdownMenu.Root>
        
        <div ref={linkButtonRef}>
          <IconButton 
            size="small" 
            icon={<Link />} 
            onClick={handleLinkClick}
          />
        </div>
        <div className="flex w-px flex-none flex-col items-center gap-2 self-stretch bg-neutral-border" />
        <IconButton 
          size="small" 
          icon={<List />} 
          onClick={handleToggleBulletList}
        />
        <IconButton 
          size="small" 
          icon={<ListChecks />} 
          onClick={handleToggleCheckList}
        />
        <IconButton 
          size="small" 
          icon={<ListOrdered />} 
          onClick={handleToggleOrderedList}
        />
        <div className="flex w-px flex-none flex-col items-center gap-2 self-stretch bg-neutral-border" />
        <IconButton 
          size="small" 
          icon={<Code2 />} 
          onClick={handleInsertInlineCode}
        />
        
        <div className="flex-1" />
        
        {/* View Mode Toggle Buttons */}
        <IconButton
          size="small"
          icon={<Eye />}
          variant={currentViewMode === 'rich-text' ? 'brand-primary' : 'neutral-secondary'}
          onClick={() => handleViewModeToggle('rich-text')}
        />
        <IconButton
          size="small"
          icon={<FileText />}
          variant={currentViewMode === 'source' ? 'brand-primary' : 'neutral-secondary'}
          onClick={() => handleViewModeToggle('source')}
        />
      </div>
      
      {/* LinkPopup - Now properly integrated with MDXEditor realm */}
      <LinkPopup
        visible={linkPopupVisible}
        initialUrl={linkData?.url || ''}
        initialText={linkData?.text || ''}
        onSubmit={handleLinkSubmit}
        onCancel={handleLinkCancel}
        onRemove={linkData ? handleLinkRemove : undefined}
        anchorElement={linkButtonRef.current || undefined}
      />
      
      <div className="flex w-full flex-1 flex-col items-start border border-solid border-neutral-border focus-within:border-focus-border min-h-0 overflow-hidden">
        <MDXEditor
          ref={mdxEditorRef}
          markdown={value || ''}
          onChange={onChange}
          placeholder="Write a note..."
          autoFocus={autoFocus}
          plugins={[
            headingsPlugin(),
            listsPlugin(),
            quotePlugin(),
            linkPlugin(),
            // linkDialogPlugin(),  // Disable built-in link dialog - we use our custom LinkPopup
            codeBlockPlugin({ 
              defaultCodeBlockLanguage: 'txt',
              // Add fallback editor to handle any code blocks
              codeBlockEditorDescriptors: [
                {
                  priority: -10,
                  match: () => true,
                  Editor: CodeMirrorEditor
                }
              ]
            }),
            codeMirrorPlugin({ 
              codeBlockLanguages: { 
                txt: 'Plain Text', 
                js: 'JavaScript', 
                ts: 'TypeScript', 
                py: 'Python',
                jsx: 'JavaScript (React)',
                tsx: 'TypeScript (React)',
                css: 'CSS',
                json: 'JSON',
                html: 'HTML',
                md: 'Markdown',
                bash: 'Bash',
                sh: 'Shell',
                sql: 'SQL',
                yaml: 'YAML',
                xml: 'XML'
              } 
            }),
            thematicBreakPlugin(),
            tablePlugin(),
            markdownShortcutPlugin(),
            diffSourcePlugin({ viewMode: 'rich-text' }),
            remoteRealmPlugin({ editorId }),
          ]}
          contentEditableClassName={resolvedTheme === "dark" ? "prose prose-invert" : "prose"}
          className={cn(
            "w-full mdx-editor-timeline overflow-y-scroll",
            resolvedTheme === "dark" ? "dark-theme" : "light-theme"
          )}
        />
      </div>
    </div>
    </RemoteMDXEditorRealmProvider>
  );
});

export const MarkdownInput = MarkdownInputRoot;
