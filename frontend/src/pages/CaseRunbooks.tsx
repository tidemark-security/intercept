import React, { useMemo, useState } from 'react';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { TextField } from '@/components/forms/TextField';
import { TextArea } from '@/components/forms/TextArea';
import { Select } from '@/components/forms/Select';
import { Badge } from '@/components/data-display/Badge';
import { Tag } from '@/components/data-display/Tag';
import { PicerlStage } from '@/components/misc/PicerlStage';
import { FormDrawer } from '@/components/overlays';
import { useSession } from '@/contexts/sessionContext';
import {
  useCaseRunbooks,
  useCreateCaseRunbook,
  useDeleteCaseRunbook,
  useDisableCaseRunbook,
  usePublishCaseRunbook,
  useUpdateCaseRunbook,
} from '@/hooks/useCaseRunbooks';
import type { CaseRunbookPayload, CaseRunbookRead, CaseRunbookStatus, PICERLStage, RunbookTaskDefinition } from '@/types/caseRunbooks';
import { PICERL_STAGES, PICERL_STAGE_LABELS } from '@/types/caseRunbooks';
import { cn } from '@/utils/cn';
import { ArrowDown, ArrowUp, Edit3, Plus, Save, Trash2, X } from 'lucide-react';

const PRIORITIES: NonNullable<RunbookTaskDefinition['priority']>[] = ['INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'EXTREME'];
const PRIORITY_UNSET = '__unset__';

function emptyTask(): RunbookTaskDefinition {
  return {
    title: '',
    description: '',
    picerl_stage: 'Preparation',
    relative_due_seconds: null,
    priority: null,
    tags: [],
  };
}

function runbookToDraft(runbook?: CaseRunbookRead | null): CaseRunbookPayload {
  return {
    title: runbook?.title ?? '',
    description: runbook?.description ?? '',
    status: runbook?.status ?? 'DRAFT',
    case_tags: runbook?.case_tags ?? [],
    runbook_tasks: runbook?.runbook_tasks?.length ? runbook.runbook_tasks : [emptyTask()],
  };
}

function parseTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean);
}

type EditorMode = 'create' | 'edit' | null;

export default function CaseRunbooksPage() {
  const { isAdmin } = useSession();
  const [includeDrafts, setIncludeDrafts] = useState(false);
  const [includeDisabled, setIncludeDisabled] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editorMode, setEditorMode] = useState<EditorMode>(null);
  const [draft, setDraft] = useState<CaseRunbookPayload>(() => runbookToDraft(null));

  const statuses = useMemo<CaseRunbookStatus[]>(() => {
    const next: CaseRunbookStatus[] = ['PUBLISHED'];
    if (includeDrafts) next.push('DRAFT');
    if (includeDisabled) next.push('DISABLED');
    return next;
  }, [includeDisabled, includeDrafts]);

  const { data, isLoading, error } = useCaseRunbooks(statuses, search || null);
  const runbooks = data?.items ?? [];
  const selectedRunbook = runbooks.find((runbook) => runbook.id === selectedId) ?? runbooks[0] ?? null;

  React.useEffect(() => {
    if (selectedRunbook && selectedId === null) {
      setSelectedId(selectedRunbook.id);
    }
  }, [selectedId, selectedRunbook]);

  const createMutation = useCreateCaseRunbook();
  const updateMutation = useUpdateCaseRunbook();
  const publishMutation = usePublishCaseRunbook();
  const disableMutation = useDisableCaseRunbook();
  const deleteMutation = useDeleteCaseRunbook();
  const busy = createMutation.isPending || updateMutation.isPending || publishMutation.isPending || disableMutation.isPending || deleteMutation.isPending;
  const isEditing = editorMode !== null;

  const openCreate = () => {
    setEditorMode('create');
    setDraft(runbookToDraft(null));
  };

  const openEdit = () => {
    if (!selectedRunbook) return;
    setEditorMode('edit');
    setDraft(runbookToDraft(selectedRunbook));
  };

  const closeEditor = () => {
    setEditorMode(null);
    setDraft(runbookToDraft(selectedRunbook));
  };

  const updateTask = (index: number, patch: Partial<RunbookTaskDefinition>) => {
    setDraft((current) => ({
      ...current,
      runbook_tasks: (current.runbook_tasks ?? []).map((task, taskIndex) =>
        taskIndex === index ? { ...task, ...patch } : task
      ),
    }));
  };

  const moveTask = (index: number, direction: -1 | 1) => {
    setDraft((current) => {
      const tasks = [...(current.runbook_tasks ?? [])];
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= tasks.length) return current;
      [tasks[index], tasks[nextIndex]] = [tasks[nextIndex], tasks[index]];
      return { ...current, runbook_tasks: tasks };
    });
  };

  const save = async () => {
    const payload = {
      ...draft,
      case_tags: draft.case_tags ?? [],
      runbook_tasks: draft.runbook_tasks ?? [],
    };
    if (editorMode === 'create') {
      const created = await createMutation.mutateAsync(payload);
      setIncludeDrafts(true);
      setSelectedId(created.id);
      setEditorMode(null);
      return;
    }
    if (editorMode === 'edit' && selectedRunbook) {
      await updateMutation.mutateAsync({ id: selectedRunbook.id, payload });
      setEditorMode(null);
    }
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="mx-auto flex h-full w-full max-w-[1536px] flex-col items-start gap-6 px-6 py-8 mobile:px-4">
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-heading-1 font-heading-1 text-default-font">Case Runbooks</span>
            <span className="text-body text-subtext-color">Reusable response work structures</span>
          </div>
          {isAdmin ? (
            <Button variant="brand-primary" icon={<Plus />} onClick={openCreate}>
              New Runbook
            </Button>
          ) : null}
        </div>

        <div className="grid min-h-[640px] w-full grid-cols-[minmax(280px,360px)_1fr] gap-4 mobile:grid-cols-1">
          <div className="flex min-w-0 flex-col gap-3 border border-neutral-border bg-default-background p-3">
            <TextField className="h-auto w-full" label="Search">
              <TextField.Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search runbooks" />
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
              {isLoading ? <span className="p-3 text-body text-subtext-color">Loading runbooks...</span> : null}
              {error ? <span className="p-3 text-body text-error-color">Failed to load runbooks</span> : null}
              {runbooks.map((runbook) => (
                <button
                  key={runbook.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(runbook.id);
                    setEditorMode(null);
                  }}
                  className={cn(
                    'flex w-full flex-col gap-2 border border-neutral-border p-3 text-left hover:border-brand-primary',
                    selectedRunbook?.id === runbook.id && 'border-brand-primary bg-brand-1100'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-heading-3 font-heading-3 text-default-font">{runbook.title}</span>
                    <Badge>{runbook.status}</Badge>
                  </div>
                  <span className="text-caption font-caption text-subtext-color">{runbook.human_id} · {runbook.runbook_tasks.length} tasks</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex min-w-0 flex-col gap-4 border border-neutral-border bg-default-background p-4">
            {selectedRunbook ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="text-heading-2 font-heading-2 text-default-font">{selectedRunbook.title}</span>
                    <span className="text-caption font-caption text-subtext-color">{selectedRunbook.human_id}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge>{selectedRunbook.status}</Badge>
                    {isAdmin ? (
                      <Button size="small" variant="neutral-secondary" icon={<Edit3 />} onClick={openEdit} disabled={busy}>
                        Edit
                      </Button>
                    ) : null}
                    {isAdmin && selectedRunbook.status !== 'PUBLISHED' ? (
                      <Button size="small" variant="brand-secondary" onClick={() => publishMutation.mutate(selectedRunbook.id)} disabled={busy}>
                        Publish
                      </Button>
                    ) : null}
                    {isAdmin && selectedRunbook.status === 'PUBLISHED' ? (
                      <Button size="small" variant="neutral-secondary" onClick={() => disableMutation.mutate(selectedRunbook.id)} disabled={busy}>
                        Disable
                      </Button>
                    ) : null}
                    {isAdmin ? (
                      <Button size="small" variant="destructive-secondary" icon={<Trash2 />} onClick={() => deleteMutation.mutate(selectedRunbook.id)} disabled={busy}>
                        Delete
                      </Button>
                    ) : null}
                  </div>
                </div>

                {selectedRunbook.description ? (
                  <p className="text-body text-default-font">{selectedRunbook.description}</p>
                ) : null}

                <div className="flex flex-wrap gap-1">
                  {(selectedRunbook.case_tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                </div>

                <div className="flex flex-col gap-3">
                  <span className="text-heading-3 font-heading-3 text-default-font">Runbook Tasks</span>
                  {selectedRunbook.runbook_tasks.map((task, index) => (
                    <div key={`${task.title}-${index}`} className="flex flex-col gap-2 border border-neutral-border p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-body-bold font-body-bold text-default-font">{task.title}</span>
                        <PicerlStage stage={task.picerl_stage} />
                        {task.priority ? <Badge>{task.priority}</Badge> : null}
                      </div>
                      {task.description ? <span className="text-caption font-caption text-subtext-color">{task.description}</span> : null}
                      <div className="flex flex-wrap gap-1">
                        {(task.tags ?? []).map((tag) => <Tag key={tag}>{tag}</Tag>)}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="flex h-full items-center justify-center text-body text-subtext-color">No runbooks found</div>
            )}
          </div>

        </div>
      </div>

      <FormDrawer
        open={isEditing}
        title={editorMode === 'create' ? 'New Case Runbook' : 'Edit Case Runbook'}
        description="Define the case tags and task sequence analysts can apply during response."
        widthClassName="w-[640px]"
        closeLabel="Close runbook drawer"
        onOpenChange={(open) => {
          if (!open && !busy) {
            closeEditor();
          }
        }}
        footer={
          <div className="flex w-full items-center gap-2">
            <Button className="flex-1" variant="neutral-secondary" icon={<X />} onClick={closeEditor} disabled={busy}>
              Cancel
            </Button>
            <Button className="flex-1" iconRight={<Save />} onClick={save} disabled={busy || !(draft.title ?? '').trim()} loading={busy}>
              {editorMode === 'create' ? 'Create Runbook' : 'Save Changes'}
            </Button>
          </div>
        }
      >
        <TextField className="h-auto w-full flex-none" label="Runbook Title" helpText="Short response pattern name">
          <TextField.Input value={draft.title ?? ''} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} placeholder="Credential theft response" />
        </TextField>

        <TextArea className="h-auto w-full flex-none" label="Description" helpText="Markdown supported">
          <TextArea.Input className="min-h-24" value={draft.description ?? ''} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="When to use this runbook and what it covers" />
        </TextArea>

        <TextField className="h-auto w-full flex-none" label="Case Tags" helpText="Comma-separated tags added to the case">
          <TextField.Input value={(draft.case_tags ?? []).join(', ')} onChange={(event) => setDraft((current) => ({ ...current, case_tags: parseTags(event.target.value) }))} placeholder="credential-theft, identity" />
        </TextField>

        <div className="flex w-full flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-heading-3 font-heading-3 text-default-font">Runbook Tasks</span>
            <Button size="small" variant="neutral-secondary" icon={<Plus />} onClick={() => setDraft((current) => ({ ...current, runbook_tasks: [...(current.runbook_tasks ?? []), emptyTask()] }))}>
              Add Task
            </Button>
          </div>
          {(draft.runbook_tasks ?? []).map((task, index) => (
            <div key={index} className="flex w-full flex-col gap-3 border border-solid border-neutral-border bg-default-background p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-caption-bold font-caption-bold text-subtext-color">Task {index + 1}</span>
                <div className="flex items-center gap-1">
                  <IconButton aria-label="Move task up" size="small" variant="neutral-tertiary" icon={<ArrowUp />} disabled={index === 0} onClick={() => moveTask(index, -1)} />
                  <IconButton aria-label="Move task down" size="small" variant="neutral-tertiary" icon={<ArrowDown />} disabled={index === (draft.runbook_tasks ?? []).length - 1} onClick={() => moveTask(index, 1)} />
                </div>
              </div>

              <TextField className="h-auto w-full" label="Task Title">
                <TextField.Input value={task.title} onChange={(event) => updateTask(index, { title: event.target.value })} placeholder="Review identity provider logs" />
              </TextField>

              <TextArea className="h-auto w-full" label="Task Details">
                <TextArea.Input value={task.description ?? ''} onChange={(event) => updateTask(index, { description: event.target.value })} placeholder="Optional task instructions" />
              </TextArea>

              <Select className="h-auto w-full" label="PICERL Stage" value={task.picerl_stage} onValueChange={(stage) => updateTask(index, { picerl_stage: stage as PICERLStage })}>
                {PICERL_STAGES.map((stage) => (
                  <Select.Item key={stage} value={stage}>{PICERL_STAGE_LABELS[stage]}</Select.Item>
                ))}
              </Select>

              <Select className="h-auto w-full" label="Priority" value={task.priority ?? PRIORITY_UNSET} onValueChange={(priority) => updateTask(index, { priority: priority === PRIORITY_UNSET ? null : priority as RunbookTaskDefinition['priority'] })}>
                <Select.Item value={PRIORITY_UNSET}>Case priority</Select.Item>
                {PRIORITIES.map((priority) => <Select.Item key={priority} value={priority}>{priority}</Select.Item>)}
              </Select>

              <TextField className="h-auto w-full" label="Relative Due Seconds">
                <TextField.Input type="number" value={task.relative_due_seconds == null ? '' : String(task.relative_due_seconds)} onChange={(event) => updateTask(index, { relative_due_seconds: event.target.value ? Number(event.target.value) : null })} placeholder="86400" />
              </TextField>

              <TextField className="h-auto w-full" label="Task Tags">
                <TextField.Input value={(task.tags ?? []).join(', ')} onChange={(event) => updateTask(index, { tags: parseTags(event.target.value) })} placeholder="identity, containment" />
              </TextField>
            </div>
          ))}
        </div>
      </FormDrawer>
    </DefaultPageLayout>
  );
}
