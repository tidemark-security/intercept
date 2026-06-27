import React, { useMemo, useState } from 'react';
import { Button } from '@/components/buttons/Button';
import { TextField } from '@/components/forms/TextField';
import { AssigneeSelector } from '@/components/forms/AssigneeSelector';
import { Badge } from '@/components/data-display/Badge';
import { PicerlStage } from '@/components/misc/PicerlStage';
import { Tag } from '@/components/data-display/Tag';
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';
import { useCaseDetail } from '@/hooks/useCaseDetail';
import { useCaseTemplates, useApplyCaseTemplate } from '@/hooks/useCaseTemplates';
import { useUsers } from '@/hooks/useUsers';
import { useSession } from '@/contexts/sessionContext';
import { getTimelineItems } from '@/utils/timelineHelpers';
import type { CaseTemplateRead, TemplateTaskOverride } from '@/types/caseTemplates';
import { AlertTriangle, CheckSquare, Square } from 'lucide-react';

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

export function CaseTemplateApplyForm() {
  const { caseId, onSuccess, onCancel } = useTimelineFormContext();
  const { user } = useSession();
  const currentUser = user?.username ?? null;
  const [search, setSearch] = useState('');
  const { data: templatesData, isLoading } = useCaseTemplates(['PUBLISHED'], search || null);
  const templates = templatesData?.items ?? [];
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const selectedTemplate: CaseTemplateRead | null =
    templates.find((template) => template.id === selectedTemplateId) ?? templates[0] ?? null;
  const { data: caseDetail } = useCaseDetail(caseId ?? null, { includeLinkedTimelines: true });
  const { data: users = [], isLoading: usersLoading } = useUsers({});
  const applyMutation = useApplyCaseTemplate(caseId ?? null);
  const [overrides, setOverrides] = useState<Record<number, TemplateTaskOverride>>({});
  const [applyError, setApplyError] = useState<string | null>(null);

  React.useEffect(() => {
    if (selectedTemplate && selectedTemplateId === null) {
      setSelectedTemplateId(selectedTemplate.id);
    }
  }, [selectedTemplate, selectedTemplateId]);

  React.useEffect(() => {
    setOverrides({});
  }, [selectedTemplate?.id]);

  const existingTaskTitles = useMemo(() => {
    const titles = new Set<string>();
    getTimelineItems(caseDetail ?? null).forEach((item) => {
      if (item.type === 'task' && 'title' in item && typeof item.title === 'string') {
        titles.add(taskTitleKey(item.title));
      }
    });
    return titles;
  }, [caseDetail]);

  const tasks = selectedTemplate?.template_tasks ?? [];
  const selectedCount = tasks.filter((_, index) => overrides[index]?.selected !== false).length;

  const setOverride = (index: number, patch: Partial<TemplateTaskOverride>) => {
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
    if (!selectedTemplate || selectedCount === 0) return;
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
        templateId: selectedTemplate.id,
        taskOverrides,
      });
      onSuccess?.(result.created_task_ids[0] ? `linked-task-${result.created_task_ids[0]}` : undefined);
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : 'Failed to apply case template');
    }
  };

  return (
    <div className="flex w-full flex-col gap-4 p-4">
      <div className="flex flex-col gap-1">
        <span className="text-heading-2 font-heading-2 text-default-font">Case Template</span>
        <span className="text-caption font-caption text-subtext-color">Apply published response work to this case</span>
      </div>

      <TextField className="h-auto w-full">
        <TextField.Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search published templates" />
      </TextField>

      <div className="flex max-h-48 flex-col gap-2 overflow-auto border border-neutral-border p-2">
        {isLoading ? <span className="text-body text-subtext-color">Loading templates...</span> : null}
        {templates.map((template) => (
          <button
            key={template.id}
            type="button"
            className={`flex flex-col gap-1 border p-2 text-left ${selectedTemplate?.id === template.id ? 'border-brand-primary bg-brand-1100' : 'border-neutral-border'}`}
            onClick={() => setSelectedTemplateId(template.id)}
          >
            <span className="text-body-bold font-body-bold text-default-font">{template.title}</span>
            <span className="text-caption font-caption text-subtext-color">{template.human_id} · {template.template_tasks.length} tasks</span>
          </button>
        ))}
      </div>

      {selectedTemplate ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1">
            {(selectedTemplate.case_tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
          </div>
          {tasks.map((task, index) => {
            const selected = overrides[index]?.selected !== false;
            const duplicate = existingTaskTitles.has(taskTitleKey(task.title));
            const dueDate = overrides[index]?.due_date ?? computeDueDate(task.relative_due_seconds);
            return (
              <div key={`${task.title}-${index}`} className="flex flex-col gap-3 border border-neutral-border p-3">
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

      <div className="flex gap-2 border-t border-neutral-border pt-4">
        <Button
          variant="brand-primary"
          className="flex-1"
          data-testid="case-template-apply-button"
          onClick={handleApply}
          disabled={!selectedTemplate || selectedCount === 0 || applyMutation.isPending}
        >
          Apply
        </Button>
        <Button variant="neutral-secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}
