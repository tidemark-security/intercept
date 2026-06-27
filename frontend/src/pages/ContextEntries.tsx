import { FormEvent, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, RefreshCw, Save, Search, Trash2, X } from 'lucide-react';

import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';
import { Badge } from '@/components/data-display/Badge';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { DateTimeManager } from '@/components/forms/DateTimeManager';
import { MarkdownInput } from '@/components/forms/MarkdownInput';
import { TextField } from '@/components/forms/TextField';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Drawer } from '@/components/overlays/Drawer';
import { useSession } from '@/contexts/sessionContext';
import { useToast } from '@/contexts/ToastContext';
import { Switch } from '@tidemark-security/ux';
import {
  ContextCriterion,
  ContextCriterionType,
  ContextEntry,
  ContextEntryPayload,
  createContextEntry,
  expireContextEntry,
  listContextEntries,
  updateContextEntry,
} from '@/services/contextEntriesApi';

const QUERY_KEY = ['context-entries'] as const;

const CRITERION_OPTIONS: { value: ContextCriterionType; label: string; placeholder: string }[] = [
  { value: 'ALERT_SOURCE', label: 'Alert source', placeholder: 'edr-*' },
  { value: 'ACTOR', label: 'Actor', placeholder: 'secops-?' },
  { value: 'SYSTEM', label: 'System', placeholder: '*.corp.local' },
  { value: 'OBSERVABLE', label: 'Observable', placeholder: 'prod-*' },
  { value: 'TAG', label: 'Tag', placeholder: 'credential-*' },
];

type DrawerMode = 'create' | 'edit' | null;

interface FormState {
  criteria: ContextCriterion[];
  body: string;
  expiresAt: string;
}

const emptyForm: FormState = {
  criteria: [],
  body: '',
  expiresAt: '',
};

function toLocalInputValue(value: string): string {
  const date = new Date(value);
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16).replace('T', ' ');
}

function buildPayload(form: FormState): ContextEntryPayload {
  return {
    criteria: form.criteria.map((criterion) => ({
      type: criterion.type,
      value: criterion.value.trim(),
    })),
    body: form.body.trim(),
    expires_at: new Date(form.expiresAt.replace(' ', 'T')).toISOString(),
  };
}

function criterionOption(type: ContextCriterionType) {
  return CRITERION_OPTIONS.find((item) => item.value === type);
}

function criteriaLabel(entry: ContextEntry): string {
  if (entry.criteria.length === 0) return 'All alerts';
  return entry.criteria
    .map((criterion) => `${criterionOption(criterion.type)?.label ?? criterion.type}: ${criterion.value}`)
    .join(' + ');
}

function isExpired(entry: ContextEntry): boolean {
  return Boolean(entry.expired_at) || new Date(entry.expires_at).getTime() <= Date.now();
}

function entryMatchesSearch(entry: ContextEntry, searchQuery: string): boolean {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return true;

  return [criteriaLabel(entry), entry.body, entry.author]
    .some((value) => value.toLowerCase().includes(query));
}

export default function ContextEntries() {
  const { isAuditor } = useSession();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [drawerMode, setDrawerMode] = useState<DrawerMode>(null);
  const [showExpired, setShowExpired] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const contextQuery = useQuery({
    queryKey: [...QUERY_KEY, showExpired],
    queryFn: () => listContextEntries(showExpired),
  });

  const resetForm = () => {
    setForm(emptyForm);
    setEditingId(null);
    setDrawerMode(null);
  };

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const saveMutation = useMutation({
    mutationFn: (payload: ContextEntryPayload) =>
      editingId ? updateContextEntry(editingId, payload) : createContextEntry(payload),
    onSuccess: () => {
      showToast('Context entry saved', undefined, 'success');
      resetForm();
      invalidate();
    },
    onError: (error: Error) => showToast('Unable to save context', error.message, 'error'),
  });

  const expireMutation = useMutation({
    mutationFn: expireContextEntry,
    onSuccess: () => {
      showToast('Context entry expired', undefined, 'success');
      invalidate();
    },
    onError: (error: Error) => showToast('Unable to expire context', error.message, 'error'),
  });

  const entries = contextQuery.data ?? [];
  const filteredEntries = useMemo(() => entries.filter((entry) => {
    return entryMatchesSearch(entry, searchQuery);
  }), [entries, searchQuery]);

  const canSave = useMemo(() => {
    const criteriaValid = form.criteria.every((criterion) => criterion.value.trim().length > 0);
    return !isAuditor && criteriaValid && form.body.trim().length > 0 && form.expiresAt.length > 0;
  }, [form, isAuditor]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    saveMutation.mutate(buildPayload(form));
  };

  const openCreateDrawer = () => {
    setForm(emptyForm);
    setEditingId(null);
    setDrawerMode('create');
  };

  const startEdit = (entry: ContextEntry) => {
    setEditingId(entry.id);
    setForm({
      criteria: entry.criteria.map((criterion) => ({ ...criterion })),
      body: entry.body,
      expiresAt: toLocalInputValue(entry.expires_at),
    });
    setDrawerMode('edit');
  };

  const addCriterion = () => {
    setForm((current) => ({
      ...current,
      criteria: [...current.criteria, { type: 'ALERT_SOURCE', value: '' }],
    }));
  };

  const updateCriterion = (index: number, patch: Partial<ContextCriterion>) => {
    setForm((current) => ({
      ...current,
      criteria: current.criteria.map((criterion, criterionIndex) => (
        criterionIndex === index ? { ...criterion, ...patch } : criterion
      )),
    }));
  };

  const removeCriterion = (index: number) => {
    setForm((current) => ({
      ...current,
      criteria: current.criteria.filter((_, criterionIndex) => criterionIndex !== index),
    }));
  };

  const drawerTitle = drawerMode === 'edit' ? 'Edit context entry' : 'Create context entry';
  const drawerDescription = 'Shared instructions that apply when alerts match the selected criteria.';

  return (
    <DefaultPageLayout withContainer>
      <div className="mx-auto flex h-full w-full max-w-[1536px] flex-col items-start gap-6 px-6 py-8 mobile:px-4">
        <div className="flex w-full flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-heading-1 font-heading-1 text-default-font">Context Entries</span>
            <span className="text-body text-subtext-color">Shared context applied to matching workflows</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {!isAuditor && (
              <Button icon={<Plus />} onClick={openCreateDrawer}>
                Create context entry
              </Button>
            )}
          </div>
        </div>

        <div className="flex w-full flex-wrap items-end gap-3 rounded-md border border-neutral-border bg-default-background p-3">
          <TextField className="min-w-72 flex-1" icon={<Search />}>
            <input
              className="h-full w-full bg-transparent text-body text-default-font outline-none placeholder:text-subtext-color"
              placeholder="Search context entries..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </TextField>
          <label className="flex h-8 items-center gap-2 rounded-md border border-neutral-border bg-default-background px-3 text-body text-subtext-color">
            <Switch
              checked={showExpired}
              onCheckedChange={setShowExpired}
              aria-label="Show expired context entries"
            />
            <span>Show expired</span>
          </label>
          <Button
            className="ml-auto"
            variant="neutral-secondary"
            icon={<RefreshCw />}
            loading={contextQuery.isFetching}
            onClick={() => contextQuery.refetch()}
          >
            Refresh
          </Button>
        </div>

        <div className="w-full overflow-hidden rounded-md border border-neutral-border bg-default-background">
          <div className="overflow-x-auto">
            <div className="min-w-[860px]">
              <div className="grid grid-cols-[minmax(220px,300px)_1fr_180px_150px] border-b border-neutral-border px-4 py-3 text-caption-bold font-caption-bold text-subtext-color">
                <span>Criteria</span>
                <span>Body</span>
                <span>Expiry</span>
                <span>Actions</span>
              </div>
              {contextQuery.isLoading ? (
                <div className="px-4 py-6 text-body text-subtext-color">Loading context</div>
              ) : filteredEntries.length === 0 ? (
                <div className="px-4 py-6 text-body text-subtext-color">
                  {entries.length === 0 ? 'No context entries' : 'No entries match the current filters'}
                </div>
              ) : (
                filteredEntries.map((entry) => {
                  const expired = isExpired(entry);
                  return (
                    <div key={entry.id} className="grid grid-cols-[minmax(220px,300px)_1fr_180px_150px] gap-4 border-b border-neutral-border px-4 py-4 last:border-b-0">
                      <div className="flex min-w-0 flex-col gap-2">
                        <div className="flex flex-wrap gap-1">
                          {entry.criteria.length === 0 ? (
                            <Badge variant="neutral">All alerts</Badge>
                          ) : entry.criteria.map((criterion, index) => (
                            <Badge key={`${criterion.type}-${criterion.value}-${index}`} variant="neutral">
                              {criterionOption(criterion.type)?.label ?? criterion.type}: {criterion.value}
                            </Badge>
                          ))}
                        </div>
                        <span className="text-caption text-subtext-color">by {entry.author}</span>
                      </div>
                      <p className="whitespace-pre-wrap break-words text-body text-default-font">{entry.body}</p>
                      <div className="flex flex-col gap-1">
                        <Badge variant={expired ? 'neutral' : 'brand'}>{expired ? 'Expired' : 'Active'}</Badge>
                        <RelativeTime value={entry.expires_at} />
                      </div>
                      <div className="flex items-start gap-2">
                        {!isAuditor && (
                          <>
                            <Button size="small" variant="neutral-secondary" icon={<Pencil />} onClick={() => startEdit(entry)}>
                              Edit
                            </Button>
                            {!expired && (
                              <Button
                                size="small"
                                variant="destructive-secondary"
                                icon={<X />}
                                loading={expireMutation.isPending}
                                onClick={() => expireMutation.mutate(entry.id)}
                              >
                                Expire
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      <Drawer open={drawerMode !== null} onOpenChange={(open) => !open && resetForm()}>
        <Drawer.Content className="w-[440px] max-w-full p-0 mobile:w-full">
          <form className="flex h-full w-full flex-col gap-6 p-4" onSubmit={handleSubmit}>
            <div className="flex w-full items-start gap-3">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <Drawer.Title className="text-heading-3 font-heading-3 text-default-font">
                  {drawerTitle}
                </Drawer.Title>
                <Drawer.Description className="text-caption font-caption text-subtext-color">
                  {drawerDescription}
                </Drawer.Description>
              </div>
              <IconButton icon={<X />} aria-label="Close context entry drawer" onClick={resetForm} />
            </div>

            <div className="flex min-h-0 w-full grow flex-col gap-6 overflow-y-auto border border-neutral-border bg-default-background p-4">
              <section className="flex w-full flex-col gap-2">
                <div className="flex flex-col gap-1">
                  <span className="text-caption-bold font-caption-bold text-default-font">Context body</span>
                  <span className="text-caption font-caption text-subtext-color">
                    Markdown supported. This context is injected into matching workflows.
                  </span>
                </div>
                <MarkdownInput
                  className="min-h-[180px] w-full"
                  variant="compact"
                  value={form.body}
                  onChange={(value) => setForm((current) => ({ ...current, body: value ?? '' }))}
                  autoFocus={drawerMode === 'create'}
                />
              </section>

              <section className="flex w-full flex-col gap-3">
                <div className="flex flex-col gap-1">
                  <span className="text-caption-bold font-caption-bold text-default-font">Matching criteria</span>
                  <span className="text-caption font-caption text-subtext-color">
                    Use * and ? as wildcards. With no criteria, this applies to all alerts.
                  </span>
                </div>
                <div className="flex w-full flex-col gap-2 rounded-md border border-neutral-border bg-neutral-50/30 p-3">
                  {form.criteria.length === 0 ? (
                    <div className="flex flex-col gap-1 rounded-md border border-dashed border-neutral-border p-3">
                      <span className="text-body-bold font-body-bold text-default-font">All alerts</span>
                      <span className="text-caption font-caption text-subtext-color">
                        Add a criterion to narrow when this context appears.
                      </span>
                    </div>
                  ) : form.criteria.map((criterion, index) => {
                    const option = criterionOption(criterion.type);
                    return (
                      <div key={`${criterion.type}-${index}`} className="grid w-full gap-2 sm:grid-cols-[150px_1fr_auto]">
                        <select
                          className="h-8 rounded-md border border-neutral-border bg-default-background px-2 text-body text-default-font outline-none focus:border-focus-border"
                          value={criterion.type}
                          onChange={(event) => updateCriterion(index, { type: event.target.value as ContextCriterionType, value: '' })}
                        >
                          {CRITERION_OPTIONS.map((item) => (
                            <option key={item.value} value={item.value}>{item.label}</option>
                          ))}
                        </select>
                        <input
                          className="h-8 rounded-md border border-neutral-border bg-default-background px-2 text-body text-default-font outline-none placeholder:text-subtext-color focus:border-focus-border"
                          placeholder={option?.placeholder ?? 'prod-*'}
                          value={criterion.value}
                          onChange={(event) => updateCriterion(index, { value: event.target.value })}
                        />
                        <IconButton
                          icon={<Trash2 />}
                          variant="destructive-tertiary"
                          aria-label="Remove criterion"
                          onClick={() => removeCriterion(index)}
                        />
                      </div>
                    );
                  })}
                  <div>
                    <Button type="button" variant="neutral-secondary" icon={<Plus />} onClick={addCriterion}>
                      Add criterion
                    </Button>
                  </div>
                </div>
              </section>

              <section className="flex w-full flex-col gap-2">
                <DateTimeManager
                  value={form.expiresAt}
                  onChange={(value) => setForm((current) => ({ ...current, expiresAt: value }))}
                  label="Expires"
                  helpText="Context stops applying after this local time."
                  showNowButton={false}
                />
              </section>
            </div>

            <div className="flex w-full gap-2">
              <Button className="flex-1" type="button" variant="neutral-secondary" icon={<X />} onClick={resetForm}>
                Cancel
              </Button>
              <Button
                className="flex-1"
                type="submit"
                icon={drawerMode === 'edit' ? <Save /> : <Plus />}
                disabled={!canSave || saveMutation.isPending}
                loading={saveMutation.isPending}
              >
                {drawerMode === 'edit' ? 'Save context entry' : 'Create context entry'}
              </Button>
            </div>
          </form>
        </Drawer.Content>
      </Drawer>
    </DefaultPageLayout>
  );
}
