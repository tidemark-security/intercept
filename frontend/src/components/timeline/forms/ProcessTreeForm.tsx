import { TextArea, TextField } from '@tidemark-security/ux';
import { GitFork } from 'lucide-react';
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';
import { useTimelineForm } from '@/hooks/useTimelineForm';
import { ApiError } from '@/types/generated/core/ApiError';
import type { ProcessTreeItem } from '@/types/generated/models/ProcessTreeItem';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { TimelineFormLayout } from '../TimelineFormLayout';

function readProcesses(value: string): ProcessTreeNode[] {
  let processes: unknown;
  try {
    processes = JSON.parse(value);
  } catch {
    throw new Error('Enter valid JSON.');
  }
  if (!Array.isArray(processes)) {
    throw new Error('Expected a JSON array of processes.');
  }
  const ids = new Set<string>();
  for (const [index, process] of processes.entries()) {
    if (!process || typeof process.id !== 'string' || !process.id.trim() ||
        typeof process.process_name !== 'string' || !process.process_name.trim() ||
        !Number.isInteger(process.process_id) || process.process_id < 0 || process.process_id > 4294967295) {
      throw new Error(`Process ${index + 1} needs an id, process name, and valid numeric PID.`);
    }
    if (ids.has(process.id)) {
      throw new Error(`Process ${index + 1} repeats an instance ID.`);
    }
    for (const field of [
      'parent_id', 'command_line', 'user_account', 'started_at',
      'verdict_reason', 'image_path', 'integrity_level', 'signer', 'sha256',
    ]) {
      if (process[field] != null && typeof process[field] !== 'string') {
        throw new Error(`Process ${index + 1} needs a text value for ${field}.`);
      }
    }
    if (process.status != null && process.status !== 'running' && process.status !== 'exited') {
      throw new Error(`Process ${index + 1} has an invalid status. Use running or exited.`);
    }
    if (process.verdict != null && !['benign', 'suspicious', 'malicious'].includes(process.verdict)) {
      throw new Error(`Process ${index + 1} has an invalid verdict. Use benign, suspicious, or malicious.`);
    }
    for (const field of ['is_alert_source', 'is_signed']) {
      if (process[field] != null && typeof process[field] !== 'boolean') {
        throw new Error(`Process ${index + 1} needs a boolean value for ${field}.`);
      }
    }
    for (const field of ['network_connections', 'file_writes']) {
      if (process[field] != null && (!Number.isInteger(process[field]) || process[field] < 0)) {
        throw new Error(`Process ${index + 1} needs a non-negative integer for ${field}.`);
      }
    }
    ids.add(process.id);
  }
  return processes as ProcessTreeNode[];
}

export function ProcessTreeForm({ initialData }: { initialData?: ProcessTreeItem }) {
  const { editMode, onCancel } = useTimelineFormContext();
  const { formState, setFormState, handleSubmit, handleClear, isSubmitting, initialFlagHighlight } = useTimelineForm({
    initialData,
    errorMessage: (error) => {
      const detail = error instanceof ApiError && error.status === 422 ? error.body?.detail : undefined;
      return typeof detail === 'string' ? detail : 'Could not save the process tree. Please try again.';
    },
    defaultState: { hostname: '', processes: '', timestamp: '' },
    transformInitialData: (item) => ({
      hostname: item.hostname ?? '',
      processes: JSON.stringify(item.processes, null, 2),
      timestamp: item.timestamp ?? '',
    }),
    validate: (state) => {
      try {
        readProcesses(state.processes);
        return { valid: true };
      } catch (error) {
        return { valid: false, error: error instanceof Error ? error.message : 'Invalid process snapshot.' };
      }
    },
    buildPayload: (state) => ({
      hostname: state.hostname.trim() || null,
      processes: readProcesses(state.processes),
      timestamp: state.timestamp || undefined,
      ...(initialData && { description: initialData.description, tags: initialData.tags }),
    }),
  });

  return (
    <TimelineFormLayout
      icon={<GitFork />}
      title={editMode ? 'Edit Process Tree' : 'Add Process Tree'}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? 'Update Process Tree' : 'Add Process Tree'}
      submitDisabled={!formState.processes.trim()}
      isSubmitting={isSubmitting}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField label="Host" helpText="Optional hostname for this snapshot" className="w-full">
        <TextField.Input
          value={formState.hostname}
          onChange={(event) => setFormState({ ...formState, hostname: event.target.value })}
        />
      </TextField>
      <TextField label="Capture time" helpText="Local time. Leave blank to use the current time." className="w-full">
        <TextField.Input
          aria-label="Capture time"
          type="datetime-local"
          step={1}
          value={formatAbsoluteTime(formState.timestamp, "yyyy-MM-dd'T'HH:mm:ss")}
          onChange={({ target }) => setFormState({
            ...formState,
            timestamp: target.value ? new Date(target.value).toISOString() : '',
          })}
        />
      </TextField>
      <TextArea
        label="Processes (JSON)"
        helpText="Each entry needs an id, process_name, and numeric process_id. Set parent_id to the parent’s id and is_alert_source to true for the alert process."
        className="w-full"
      >
        <TextArea.Input
          aria-label="Processes (JSON)"
          spellCheck={false}
          className="min-h-48 w-full text-monospace-body font-monospace-body"
          placeholder={'[{ "id": "desktop", "process_name": "explorer.exe", "process_id": 4120 }]'}
          value={formState.processes}
          onChange={(event) => setFormState({ ...formState, processes: event.target.value })}
        />
      </TextArea>
    </TimelineFormLayout>
  );
}
