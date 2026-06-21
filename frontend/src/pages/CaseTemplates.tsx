import React, { useMemo, useState } from 'react';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { TextField } from '@/components/forms/TextField';
import { TextArea } from '@/components/forms/TextArea';
import { Badge } from '@/components/data-display/Badge';
import { Tag } from '@/components/data-display/Tag';
import { useSession } from '@/contexts/sessionContext';
import {
  useCaseTemplates,
  useCreateCaseTemplate,
  useDeleteCaseTemplate,
  useDisableCaseTemplate,
  usePublishCaseTemplate,
  useUpdateCaseTemplate,
} from '@/hooks/useCaseTemplates';
import type { CaseTemplatePayload, CaseTemplateRead, CaseTemplateStatus, PICERLStage, TemplateTaskDefinition } from '@/types/caseTemplates';
import { PICERL_STAGES } from '@/types/caseTemplates';
import { cn } from '@/utils/cn';
import { ArrowDown, ArrowUp, BookTemplate, Plus, Save, Trash2 } from 'lucide-react';

const PICERL_STAGE_LABELS: Record<PICERLStage, string> = {
  Preparation: 'Preparation',
  Identification: 'Identification',
  Containment: 'Containment',
  Eradication: 'Eradication',
  Recovery: 'Recovery',
  'Lessons Learned': 'Lessons Learned',
};

function emptyTask(): TemplateTaskDefinition {
  return {
    title: '',
    description: '',
    picerl_stage: 'Preparation',
    relative_due_seconds: null,
    priority: null,
    tags: [],
  };
}

function templateToDraft(template?: CaseTemplateRead | null): CaseTemplatePayload {
  return {
    title: template?.title ?? '',
    description: template?.description ?? '',
    status: template?.status ?? 'DRAFT',
    case_tags: template?.case_tags ?? [],
    template_tasks: template?.template_tasks?.length ? template.template_tasks : [emptyTask()],
  };
}

function parseTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean);
}

export default function CaseTemplatesPage() {
  const { isAdmin } = useSession();
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [includeDisabled, setIncludeDisabled] = useState(false);
  const [search, setSearch] = useState('');
  const statuses = useMemo<CaseTemplateStatus[]>(() => {
    const next: CaseTemplateStatus[] = ['PUBLISHED'];
    if (includeDrafts) next.push('DRAFT');
    if (includeDisabled) next.push('DISABLED');
    return next;
  }, [includeDisabled, includeDrafts]);

  const { data, isLoading, error } = useCaseTemplates(statuses, search || null);
  const templates = data?.items ?? [];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedTemplate = templates.find((template) => template.id === selectedId) ?? templates[0] ?? null;
  const [draft, setDraft] = useState<CaseTemplatePayload>(() => templateToDraft(null));
  const [isCreating, setIsCreating] = useState(false);

  React.useEffect(() => {
    if (selectedTemplate && !isCreating) {
      setDraft(templateToDraft(selectedTemplate));
      setSelectedId(selectedTemplate.id);
    }
  }, [isCreating, selectedTemplate?.id]);

  const createMutation = useCreateCaseTemplate();
  const updateMutation = useUpdateCaseTemplate();
  const publishMutation = usePublishCaseTemplate();
  const disableMutation = useDisableCaseTemplate();
  const deleteMutation = useDeleteCaseTemplate();

  const editable = isAdmin && (isCreating || selectedTemplate?.status !== 'DELETED');
  const busy = createMutation.isPending || updateMutation.isPending || publishMutation.isPending || disableMutation.isPending || deleteMutation.isPending;

  const updateTask = (index: number, patch: Partial<TemplateTaskDefinition>) => {
    setDraft((current) => ({
      ...current,
      template_tasks: (current.template_tasks ?? []).map((task, taskIndex) =>
        taskIndex === index ? { ...task, ...patch } : task
      ),
    }));
  };

  const moveTask = (index: number, direction: -1 | 1) => {
    setDraft((current) => {
      const tasks = [...(current.template_tasks ?? [])];
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= tasks.length) {
        return current;
      }
      [tasks[index], tasks[nextIndex]] = [tasks[nextIndex], tasks[index]];
      return { ...current, template_tasks: tasks };
    });
  };

  const save = async () => {
    const payload = {
      ...draft,
      case_tags: draft.case_tags ?? [],
      template_tasks: draft.template_tasks ?? [],
    };
    if (isCreating) {
      const created = await createMutation.mutateAsync(payload);
      setIncludeDrafts(true);
      setIsCreating(false);
      setSelectedId(created.id);
    } else if (selectedTemplate) {
      await updateMutation.mutateAsync({ id: selectedTemplate.id, payload });
    }
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="flex w-full flex-col gap-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <BookTemplate className="h-6 w-6 text-brand-primary" />
            <div className="flex flex-col">
              <h1 className="text-heading-1 font-heading-1 text-default-font">Case Templates</h1>
              <span className="text-caption font-caption text-subtext-color">Reusable response work structures</span>
            </div>
          </div>
          {isAdmin ? (
            <Button
              variant="brand-primary"
              icon={<Plus />}
              onClick={() => {
                setIsCreating(true);
                setSelectedId(null);
                setDraft(templateToDraft(null));
              }}
            >
              New Template
            </Button>
          ) : null}
        </div>

        <div className="grid min-h-[640px] grid-cols-[minmax(280px,360px)_1fr] gap-4 mobile:grid-cols-1">
          <div className="flex min-w-0 flex-col gap-3 border border-neutral-border bg-default-background p-3">
            <TextField className="h-auto w-full">
              <TextField.Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search templates" />
            </TextField>
            <div className="flex flex-wrap gap-2">
              <Button size="small" variant={includeDrafts ? 'brand-secondary' : 'neutral-secondary'} onClick={() => setIncludeDrafts((value) => !value)}>
                Draft
              </Button>
              <Button size="small" variant={includeDisabled ? 'brand-secondary' : 'neutral-secondary'} onClick={() => setIncludeDisabled((value) => !value)}>
                Disabled
              </Button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto">
              {isLoading ? <span className="p-3 text-body text-subtext-color">Loading templates...</span> : null}
              {error ? <span className="p-3 text-body text-error-color">Failed to load templates</span> : null}
              {templates.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => {
                    setIsCreating(false);
                    setSelectedId(template.id);
                    setDraft(templateToDraft(template));
                  }}
                  className={cn(
                    'flex w-full flex-col gap-2 border border-neutral-border p-3 text-left hover:border-brand-primary',
                    selectedTemplate?.id === template.id && !isCreating && 'border-brand-primary bg-brand-1100'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-heading-3 font-heading-3 text-default-font">{template.title}</span>
                    <Badge>{template.status}</Badge>
                  </div>
                  <span className="text-caption font-caption text-subtext-color">{template.human_id} · {template.template_tasks.length} tasks</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-4 border border-neutral-border bg-default-background p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-col">
                <span className="text-heading-2 font-heading-2 text-default-font">
                  {isCreating ? 'Draft Template' : selectedTemplate?.title || 'Select a template'}
                </span>
                {!isCreating && selectedTemplate ? <span className="text-caption font-caption text-subtext-color">{selectedTemplate.human_id}</span> : null}
              </div>
              {isAdmin ? (
                <div className="flex flex-wrap gap-2">
                  <Button size="small" icon={<Save />} onClick={save} disabled={!editable || busy}>
                    Save
                  </Button>
                  {!isCreating && selectedTemplate?.status !== 'PUBLISHED' ? (
                    <Button size="small" variant="brand-secondary" onClick={() => selectedTemplate && publishMutation.mutate(selectedTemplate.id)} disabled={busy}>
                      Publish
                    </Button>
                  ) : null}
                  {!isCreating && selectedTemplate?.status === 'PUBLISHED' ? (
                    <Button size="small" variant="neutral-secondary" onClick={() => selectedTemplate && disableMutation.mutate(selectedTemplate.id)} disabled={busy}>
                      Disable
                    </Button>
                  ) : null}
                  {!isCreating && selectedTemplate ? (
                    <Button size="small" variant="destructive-secondary" icon={<Trash2 />} onClick={() => deleteMutation.mutate(selectedTemplate.id)} disabled={busy}>
                      Delete
                    </Button>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-3 mobile:grid-cols-1">
              <TextField className="h-auto w-full">
                <TextField.Input disabled={!editable} value={draft.title ?? ''} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder="Template title" />
              </TextField>
              <TextField className="h-auto w-full">
                <TextField.Input disabled={!editable} value={(draft.case_tags ?? []).join(', ')} onChange={(event) => setDraft((current) => ({ ...current, case_tags: parseTags(event.target.value) }))} placeholder="Case tags" />
              </TextField>
            </div>
            <TextArea className="h-auto w-full">
              <TextArea.Input disabled={!editable} value={draft.description ?? ''} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="Description" />
            </TextArea>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-heading-3 font-heading-3 text-default-font">Template Tasks</span>
                {editable ? (
                  <Button size="small" variant="neutral-secondary" onClick={() => setDraft((current) => ({ ...current, template_tasks: [...(current.template_tasks ?? []), emptyTask()] }))}>
                    Add Task
                  </Button>
                ) : null}
              </div>
              {(draft.template_tasks ?? []).map((task, index) => (
                <div key={index} className="grid gap-3 border border-neutral-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-caption-bold font-caption-bold text-subtext-color">
                      Task {index + 1}
                    </span>
                    {editable ? (
                      <div className="flex items-center gap-1">
                        <IconButton
                          aria-label="Move task up"
                          size="small"
                          variant="neutral-tertiary"
                          icon={<ArrowUp />}
                          disabled={index === 0}
                          onClick={() => moveTask(index, -1)}
                        />
                        <IconButton
                          aria-label="Move task down"
                          size="small"
                          variant="neutral-tertiary"
                          icon={<ArrowDown />}
                          disabled={index === (draft.template_tasks ?? []).length - 1}
                          onClick={() => moveTask(index, 1)}
                        />
                      </div>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-[1fr_180px_160px] gap-2 mobile:grid-cols-1">
                    <TextField className="h-auto w-full">
                      <TextField.Input disabled={!editable} value={task.title} onChange={(event) => updateTask(index, { title: event.target.value })} placeholder="Task title" />
                    </TextField>
                    <select disabled={!editable} className="h-10 border border-neutral-border bg-default-background px-2 text-body text-default-font" value={task.picerl_stage} onChange={(event) => updateTask(index, { picerl_stage: event.target.value as PICERLStage })}>
                      {PICERL_STAGES.map((stage) => <option key={stage} value={stage}>{PICERL_STAGE_LABELS[stage]}</option>)}
                    </select>
                    <select disabled={!editable} className="h-10 border border-neutral-border bg-default-background px-2 text-body text-default-font" value={task.priority ?? ''} onChange={(event) => updateTask(index, { priority: (event.target.value || null) as TemplateTaskDefinition['priority'] })}>
                      <option value="">Case priority</option>
                      {['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'EXTREME'].map((priority) => <option key={priority} value={priority}>{priority}</option>)}
                    </select>
                  </div>
                  <TextArea className="h-auto w-full">
                    <TextArea.Input disabled={!editable} value={task.description ?? ''} onChange={(event) => updateTask(index, { description: event.target.value })} placeholder="Description" />
                  </TextArea>
                  <div className="grid grid-cols-2 gap-2 mobile:grid-cols-1">
                    <TextField className="h-auto w-full">
                      <TextField.Input disabled={!editable} type="number" value={task.relative_due_seconds == null ? '' : String(task.relative_due_seconds)} onChange={(event) => updateTask(index, { relative_due_seconds: event.target.value ? Number(event.target.value) : null })} placeholder="Relative due seconds" />
                    </TextField>
                    <TextField className="h-auto w-full">
                      <TextField.Input disabled={!editable} value={(task.tags ?? []).join(', ')} onChange={(event) => updateTask(index, { tags: parseTags(event.target.value) })} placeholder="Task tags" />
                    </TextField>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(task.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </DefaultPageLayout>
  );
}
