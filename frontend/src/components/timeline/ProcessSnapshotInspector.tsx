import { useState, type ReactNode } from 'react';
import { Badge, Button, IconButton } from '@tidemark-security/ux';
import { Check, Copy, X } from 'lucide-react';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { formatAbsoluteTime } from '@/utils/dateFormatters';

export const PROCESS_TREE_UTC_FORMAT = "MMM d, yyyy HH:mm:ss 'UTC'";

const VERDICT_BADGES = {
  benign: { label: 'Benign', variant: 'neutral' },
  suspicious: { label: 'Suspicious', variant: 'warning' },
  malicious: { label: 'Malicious', variant: 'error' },
} as const;

export function ProcessIndicators({ process }: { process: ProcessTreeNode }) {
  const verdict = process.verdict ? VERDICT_BADGES[process.verdict] : undefined;
  if (!process.is_alert_source && !verdict) return null;

  return (
    <div className="flex flex-wrap gap-1">
      {process.is_alert_source && <Badge className="h-5 px-1.5" variant="error">Alert source</Badge>}
      {verdict && <Badge className="h-5 px-1.5" variant={verdict.variant}>{verdict.label}</Badge>}
    </div>
  );
}

function DetailField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-caption font-caption text-subtext-color">{label}</dt>
      <dd className="min-w-0 break-words text-body font-body">{children}</dd>
    </>
  );
}

export function ProcessSnapshotInspector({
  process,
  parent,
  onClose,
}: {
  process: ProcessTreeNode;
  parent?: ProcessTreeNode;
  onClose: () => void;
}) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const startedAt = formatAbsoluteTime(process.started_at, PROCESS_TREE_UTC_FORMAT, 'utc');
  const hasSignals = process.is_signed != null || Boolean(process.signer) ||
    process.network_connections != null || process.file_writes != null;

  async function copyCommandLine() {
    if (!process.command_line) return;
    try {
      await navigator.clipboard.writeText(process.command_line);
      setCopyState('copied');
    } catch {
      setCopyState('error');
    }
  }

  return (
    <section aria-label="Process details" className="flex flex-col gap-3 p-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 break-words text-heading-3 font-heading-3">{process.process_name}</h3>
        <IconButton type="button" size="small" variant="neutral-tertiary" icon={<X />} aria-label="Close process details" onClick={onClose} />
      </div>
      <ProcessIndicators process={process} />
      {process.verdict_reason && <p className="break-words text-body font-body">{process.verdict_reason}</p>}
      {process.command_line && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-caption-bold font-caption-bold text-subtext-color">Command line</h4>
            <Button
              type="button" size="small" variant="neutral-tertiary"
              icon={copyState === 'copied' ? <Check /> : <Copy />}
              onClick={copyCommandLine}
              aria-label="Copy command line"
            >
              {copyState === 'copied' ? 'Copied' : 'Copy'}
            </Button>
          </div>
          <pre className="whitespace-pre-wrap break-all border border-neutral-border bg-default-background p-2 text-monospace-body font-monospace-body">{process.command_line}</pre>
          <span role="status" className={copyState === 'error' ? 'text-caption font-caption text-default-font' : 'sr-only'}>
            {copyState === 'copied' ? 'Command line copied.' : copyState === 'error' ? 'Could not copy the command line.' : ''}
          </span>
        </div>
      )}

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
        <DetailField label="PID">{process.process_id}</DetailField>
        {parent && <DetailField label="Parent">{parent.process_name} ({parent.process_id})</DetailField>}
        {process.status && <DetailField label="Status">{process.status === 'running' ? 'Running' : 'Exited'}</DetailField>}
        {process.image_path && <DetailField label="Image path">{process.image_path}</DetailField>}
        {process.user_account && <DetailField label="User">{process.user_account}</DetailField>}
        {process.integrity_level && <DetailField label="Integrity">{process.integrity_level}</DetailField>}
        {startedAt && <DetailField label="Started"><time dateTime={process.started_at ?? undefined}>{startedAt}</time></DetailField>}
        {process.sha256 && <DetailField label="SHA-256"><span className="break-all">{process.sha256}</span></DetailField>}
      </dl>
      {hasSignals && (
        <div className="flex flex-col gap-1 border-t border-neutral-border pt-2">
          <h4 className="text-caption-bold font-caption-bold text-subtext-color">Signals</h4>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
            {(process.is_signed != null || process.signer) && (
              <DetailField label="Signer">{process.is_signed === false ? 'Unsigned image' : process.signer || 'Signed image'}</DetailField>
            )}
            {process.network_connections != null && <DetailField label="Connections">{process.network_connections}</DetailField>}
            {process.file_writes != null && <DetailField label="File writes">{process.file_writes}</DetailField>}
          </dl>
        </div>
      )}
    </section>
  );
}
