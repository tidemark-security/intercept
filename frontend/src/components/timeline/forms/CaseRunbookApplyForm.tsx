import React, { useMemo, useState } from 'react';
import { TextField } from '@/components/forms/TextField';
import { AssigneeSelector } from '@/components/forms/AssigneeSelector';
import { Badge } from '@/components/data-display/Badge';
import { PicerlStage } from '@/components/misc/PicerlStage';
import { Tag } from '@/components/data-display/Tag';
import { TimelineFormLayout } from '@/components/timeline/TimelineFormLayout';
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';
import { useCaseDetail } from '@/hooks/useCaseDetail';
import { useCaseRunbooks, useApplyCaseRunbook } from '@/hooks/useCaseRunbooks';
import { useUsers } from '@/hooks/useUsers';
import { useSession } from '@/contexts/sessionContext';
import { getTimelineItems } from '@/utils/timelineHelpers';
import type { CaseRunbookRead, RunbookTaskOverride } from '@/types/caseRunbooks';
import { AlertTriangle, CheckSquare, SportShoe, Square } from 'lucide-react';

function toDatetimeLocal(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function fromDatetimeLocal(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function computeDueDate(relativeSeconds?: number | null): string {
  if (relativeSeconds === null || relativeSeconds === undefined) return '';
  return toDatetimeLocal(new Date(Date.now() + relativeSeconds * 1000));
}

function taskTitleKey(title: string): string {
  return title.trim().replace(/\s+/g, ' ').toLowerCase();
}

export function CaseRunbookApplyForm() {
  const { caseId, onSuccess, onCancel } = useTimelineFormContext();
  const { user } = useSession();
  const currentUser = user?.username ?? null;
  const [search, setSearch] = useState('');
  const { data: runbooksData, isLoading } = useCaseRunbooks(['PUBLISHED'], search || null);
  const runbooks = runbooksData?.items ?? [];
  const [selectedRunbookId, setSelectedRunbookId] = useState<number | null>(null);
  const selectedRunbook: CaseRunbookRead | null =
    runbooks.find((runbook) => runbook.id === selectedRunbookId) ?? runbooks[0] ?? null;
  const { data: caseDetail } = useCaseDetail(caseId ?? null, { includeLinkedTimelines: true });
  const { data: users = [], isLoading: usersLoading } = useUsers({});
  const applyMutation = useApplyCaseRunbook(caseId ?? null);
  const [overrides, setOverrides] = useState<Record<number, RunbookTaskOverride>>({});
  const [applyError, setApplyError] = useState<string | null>(null);

  React.useEffect(() => {
    if (selectedRunbook && selectedRunbookId === null) {
      setSelectedRunbookId(selectedRunbook.id);
    }
  }, [selectedRunbook, selectedRunbookId]);

  React.useEffect(() => {
    setOverrides({});
  }, [selectedRunbook?.id]);

  const existingTaskTitles = useMemo(() => {
    const titles = new Set<string>();
    getTimelineItems(caseDetail ?? null).forEach((item) => {
      if (item.type === 'task' && 'title' in item && typeof item.title === 'string') {
        titles.add(taskTitleKey(item.title));
      }
    });
    return titles;
  }, [caseDetail]);

  const tasks = selectedRunbook?.runbook_tasks ?? [];
  const selectedCount = tasks.filter((_, index) => overrides[index]?.selected !== false).length;

  const setOverride = (index: number, patch: Partial<RunbookTaskOverride>) => {
    setOverrides((current) => ({
      ...current,
      [index]: {
        index,
        selected: current[index]?.selected ?? true,
        assignee: current[index]?.assignee ?? null,
        due_date: current[index]?.due_date ?? null,
        ...patch,
      },
    }));
  };

  const handleApply = async () => {
    if (!selectedRunbook || selectedCount === 0) return;
    setApplyError(null);
    const taskOverrides = tasks.map((task, index) => {
      const override = overrides[index];
      const dueDateLocal = override?.due_date ?? computeDueDate(task.relative_due_seconds);
      return {
        index,
        selected: override?.selected ?? true,
        assignee: override?.assignee ?? null,
        due_date: fromDatetimeLocal(dueDateLocal),
      };
    });
    try {
      const result = await applyMutation.mutateAsync({
        runbookId: selectedRunbook.id,
        taskOverrides,
      });
      onSuccess?.(result.created_task_ids[0] ? `linked-task-${result.created_task_ids[0]}` : undefined);
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : 'Failed to apply case runbook');
    }
  };

  return (
    <TimelineFormLayout
      icon={<SportShoe className="text-neutral-600" />}
      title="Case Runbook"
      onSubmit={handleApply}
      onCancel={onCancel}
      submitLabel="Apply"
      submitIcon={<SportShoe />}
      submitDisabled={!selectedRunbook || selectedCount === 0}
      submitDataTestId="case-runbook-apply-button"
      isSubmitting={applyMutation.isPending}
      showFlagHighlight={false}
      useWell={true}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="Runbook"
        helpText="Apply published response work to this case"
      >
        <TextField.Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search published runbooks" />
      </TextField>

      <div className="flex max-h-48 w-full flex-none flex-col gap-2 overflow-auto border border-solid border-neutral-border bg-default-background p-2">
        {isLoading ? <span className="text-body text-subtext-color">Loading runbooks...</span> : null}
        {runbooks.map((runbook) => (
          <button
            key={runbook.id}
            type="button"
            className={`flex flex-col gap-1 border p-2 text-left ${selectedRunbook?.id === runbook.id ? 'border-brand-primary bg-brand-1100' : 'border-neutral-border'}`}
            onClick={() => setSelectedRunbookId(runbook.id)}
          >
            <span className="text-body-bold font-body-bold text-default-font">{runbook.title}</span>
            <span className="text-caption font-caption text-subtext-color">{runbook.human_id} · {runbook.runbook_tasks.length} tasks</span>
          </button>
        ))}
      </div>

      {selectedRunbook ? (
        <div className="flex w-full flex-col gap-3">
          <div className="flex flex-wrap gap-1">
            {(selectedRunbook.case_tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          </div>
          {tasks.map((task, index) => {
            const selected = overrides[index]?.selected !== false;
            const duplicate = existingTaskTitles.has(taskTitleKey(task.title));
            const dueDate = overrides[index]?.due_date ?? computeDueDate(task.relative_due_seconds);
            return (
              <div key={`${task.title}-${index}`} className="flex w-full flex-col gap-3 border border-solid border-neutral-border bg-default-background p-3">
                <div className="flex items-start gap-2">
                  <button type="button" onClick={() => setOverride(index, { selected: !selected })} className="mt-1 text-brand-primary">
                    {selected ? <CheckSquare className="h-5 w-5" /> : <Square className="h-5 w-5" />}
                  </button>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-body-bold font-body-bold text-default-font">{task.title}</span>
                      <PicerlStage stage={task.picerl_stage} />
                      {task.priority ? <Badge>{task.priority}</Badge> : null}
                    </div>
                    {task.description ? <span className="text-caption font-caption text-subtext-color">{task.description}</span> : null}
                    {duplicate ? (
                      <span className="inline-flex items-center gap-1 text-caption font-caption text-warning-400">
                        <AlertTriangle className="h-3.5 w-3.5" /> Duplicate task title
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 mobile:grid-cols-1">
                  <AssigneeSelector
                    currentAssignee={overrides[index]?.assignee ?? null}
                    currentUser={currentUser}
                    users={users}
                    isLoadingUsers={usersLoading}
                    onUnassign={() => setOverride(index, { assignee: null })}
                    onAssignToMe={() => setOverride(index, { assignee: currentUser })}
                    onAssignToUser={(username) => setOverride(index, { assignee: username })}
                    unassignedLabel="Unassigned"
                  />
                  <input
                    className="h-10 border border-neutral-border bg-default-background px-2 text-body text-default-font"
                    type="datetime-local"
                    value={dueDate}
                    onChange={(event) => setOverride(index, { due_date: event.target.value })}
                  />
                </div>
                <div className="flex flex-wrap gap-1">
                  {(task.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {applyError ? (
        <span className="border border-error-700 bg-error-50 px-3 py-2 text-caption font-caption text-error-1000">
          {applyError}
        </span>
      ) : null}
    </TimelineFormLayout>
  );
}
