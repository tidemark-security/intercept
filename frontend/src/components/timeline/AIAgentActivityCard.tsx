import { useId, useState, type ReactNode } from 'react';
import {
  Bot, Code, FilePenLine, FileText, Maximize2, MessageSquare, Minimize2, Orbit, Plug, Terminal,
} from 'lucide-react';
import { Tag } from '@/components/data-display/Tag';
import { Tooltip } from '@/components/overlays/Tooltip';
import type { AIAgentItem } from '@/types/generated/models/AIAgentItem';
import { cn } from '@/utils/cn';

const activities = {
  tool_call: { label: 'Tool call', icon: Plug },
  file_read: { label: 'File read', icon: FileText },
  file_write: { label: 'File write', icon: FilePenLine },
  shell_command: { label: 'Shell command', icon: Terminal },
  other: { label: 'Agent activity', icon: Bot },
} satisfies Record<AIAgentItem['activity'], { label: string; icon: typeof Bot }>;

const visualStudioCode = { label: 'Visual Studio Code', icon: Code };
const harnesses = new Map([
  ['claudecode', { label: 'Claude Code', icon: Terminal }],
  ['claudedesktop', { label: 'Claude Desktop', icon: MessageSquare }],
  ['opencode', { label: 'OpenCode', icon: Terminal }],
  ['vscode', visualStudioCode],
  ['visualstudiocode', visualStudioCode],
  ['chatgptdesktop', { label: 'ChatGPT Desktop', icon: MessageSquare }],
  ['codexcli', { label: 'Codex CLI', icon: Terminal }],
  ['codexdesktop', { label: 'Codex Desktop', icon: Code }],
  ['antigravity', { label: 'Antigravity', icon: Orbit }],
]);

const outcomeLabels = { succeeded: 'Succeeded', failed: 'Failed', blocked: 'Blocked' };

interface AIAgentActivityCardProps {
  item: AIAgentItem;
  embedded?: boolean;
  actions?: ReactNode;
}

export function AIAgentActivityCard({ item, embedded, actions }: AIAgentActivityCardProps) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();
  const harnessValue = item.harness?.trim() || '';
  const { label: harness, icon: HarnessIcon } =
    harnesses.get(harnessValue.toLowerCase().replace(/[\s_-]+/g, '')) ??
    { label: harnessValue || 'Unknown harness', icon: Bot };
  const { label: activity, icon: ActivityIcon } = activities[item.activity] ?? activities.other;
  const target = item.activity === 'shell_command'
    ? item.command_line || item.tool_name
    : item.activity === 'file_read' || item.activity === 'file_write'
      ? item.file_path || item.tool_name
      : item.tool_name;
  const outcome = item.outcome ? outcomeLabels[item.outcome] : undefined;
  const fields = [
    { label: 'Agent', value: item.agent_name },
    { label: 'Tool', value: item.tool_name, code: true },
    { label: 'File path', value: item.file_path, code: true },
    { label: 'Command', value: item.command_line, code: true },
    { label: 'Endpoint', value: item.endpoint },
    { label: 'Outcome', value: outcome },
    { label: 'Exit code', value: item.exit_code },
    { label: 'Source event', value: item.source_event_id, code: true },
  ].filter(({ value }) => value != null && value !== '');

  const toggle = (
    <button
      type="button"
      aria-label={expanded ? 'Collapse AI agent activity' : 'Expand AI agent activity'}
      aria-expanded={expanded}
      aria-controls={detailsId}
      className="nodrag nopan flex h-8 w-8 flex-none items-center justify-center rounded text-subtext-color hover:bg-neutral-200 hover:text-default-font focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      onClick={(event) => {
        event.stopPropagation();
        setExpanded(!expanded);
      }}
    >
      {expanded ? <Minimize2 size={14} aria-hidden /> : <Maximize2 size={14} aria-hidden />}
    </button>
  );

  return (
    <div className={cn(
      'w-full min-w-0 max-w-[1024px] rounded-md border border-neutral-border bg-default-background',
      embedded && 'max-w-none border-transparent bg-transparent',
    )}>
      <div className={cn(
        'flex min-w-0 items-center gap-2 px-2.5 py-1',
        expanded && 'border-b border-neutral-border px-3 py-2',
      )}>
        <span className="flex min-w-0 shrink items-center gap-1.5 rounded border border-neutral-border bg-neutral-100 px-1.5 py-0.5 text-caption-bold font-caption-bold text-default-font">
          <HarnessIcon size={13} className="flex-none" aria-hidden />
          <span className="truncate">{harness}</span>
        </span>
        <span className="flex min-w-0 shrink-0 items-center gap-1.5 text-caption-bold font-caption-bold text-default-font">
          <ActivityIcon size={14} className="flex-none text-subtext-color" aria-hidden />
          {activity}
        </span>
        {!expanded && target ? (
          <code className="min-w-0 flex-1 truncate font-mono text-caption text-subtext-color">{target}</code>
        ) : <span className="flex-1" />}
        {actions}
        <Tooltip.Provider delayDuration={250}>
          <Tooltip.Root>
            <Tooltip.Trigger asChild>{toggle}</Tooltip.Trigger>
            <Tooltip.Content side="top" align="end" className="max-w-[min(22rem,calc(100vw-2rem))]">
              <div className="min-w-0 space-y-1 break-words text-caption font-caption text-black">
                <div>{expanded ? 'Collapse activity' : [harness, item.agent_name, activity].filter(Boolean).join(' · ')}</div>
                {!expanded && target ? <code className="line-clamp-4 font-mono">{target}</code> : null}
                {!expanded && item.tool_name && target !== item.tool_name ? <div>Tool: {item.tool_name}</div> : null}
              </div>
            </Tooltip.Content>
          </Tooltip.Root>
        </Tooltip.Provider>
      </div>
      <div id={detailsId} hidden={!expanded}>
        {expanded ? (
          <div className="flex flex-col gap-3 px-3 py-3 text-body font-body text-default-font">
            {fields.length > 0 ? (
              <dl className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
                {fields.map(({ label, value, code }) => (
                  <div key={label} className={cn('min-w-0', code && 'sm:col-span-2')}>
                    <dt className="text-caption font-caption text-subtext-color">{label}</dt>
                    <dd className="whitespace-pre-wrap break-words">
                      {code ? <code className="font-mono text-caption">{value}</code> : value}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {item.description?.trim() ? (
              <p className="whitespace-pre-wrap break-words">{item.description}</p>
            ) : null}
            {item.tags?.length ? (
              <div className="flex flex-wrap gap-1.5">
                {item.tags.map((tag, index) => <Tag key={index} tagText={tag} />)}
              </div>
            ) : null}
            {fields.length === 0 && !item.description?.trim() && !item.tags?.length ? (
              <p className="text-subtext-color">No additional details recorded.</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
