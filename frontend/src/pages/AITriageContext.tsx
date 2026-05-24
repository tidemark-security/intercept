import { FormEvent, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BrainCircuit, Pencil, Save, X } from 'lucide-react';

import { Button } from '@/components/buttons/Button';
import { Badge } from '@/components/data-display/Badge';
import { RelativeTime } from '@/components/data-display/RelativeTime';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { useSession } from '@/contexts/sessionContext';
import { useToast } from '@/contexts/ToastContext';
import {
  AITriageContextEntry,
  AITriageContextPayload,
  AITriageContextScopeType,
  createAITriageContext,
  expireAITriageContext,
  listAITriageContext,
  updateAITriageContext,
} from '@/services/aiTriageContextApi';

const QUERY_KEY = ['ai-triage-context'] as const;

const SCOPE_OPTIONS: { value: AITriageContextScopeType; label: string }[] = [
  { value: 'GLOBAL', label: 'Global' },
  { value: 'ALERT_SOURCE', label: 'Alert source' },
  { value: 'CASE', label: 'Case' },
  { value: 'USER_ACCOUNT', label: 'User/account' },
  { value: 'HOST_SYSTEM', label: 'Host/system' },
  { value: 'OBSERVABLE', label: 'Observable' },
  { value: 'TAG', label: 'Tag' },
];

interface FormState {
  scopeType: AITriageContextScopeType;
  scopeValue: string;
  body: string;
  expiresAt: string;
}

const emptyForm: FormState = {
  scopeType: 'GLOBAL',
  scopeValue: '',
  body: '',
  expiresAt: '',
};

function toLocalInputValue(value: string): string {
  const date = new Date(value);
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function buildPayload(form: FormState): AITriageContextPayload {
  return {
    scope: {
      type: form.scopeType,
      value: form.scopeType === 'GLOBAL' ? null : form.scopeValue.trim(),
    },
    body: form.body.trim(),
    expires_at: new Date(form.expiresAt).toISOString(),
  };
}

function scopeLabel(entry: AITriageContextEntry): string {
  const option = SCOPE_OPTIONS.find((item) => item.value === entry.scope.type);
  if (entry.scope.type === 'GLOBAL') return option?.label ?? 'Global';
  return `${option?.label ?? entry.scope.type}: ${entry.scope.value ?? ''}`;
}

export default function AITriageContext() {
  const { isAuditor } = useSession();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showExpired, setShowExpired] = useState(false);

  const contextQuery = useQuery({
    queryKey: [...QUERY_KEY, showExpired],
    queryFn: () => listAITriageContext(showExpired),
  });

  const resetForm = () => {
    setForm(emptyForm);
    setEditingId(null);
  };

  const invalidate = () => queryClient.invalidateQueries({ queryKey: QUERY_KEY });

  const saveMutation = useMutation({
    mutationFn: (payload: AITriageContextPayload) =>
      editingId ? updateAITriageContext(editingId, payload) : createAITriageContext(payload),
    onSuccess: () => {
      showToast('AI triage context saved', undefined, 'success');
      resetForm();
      invalidate();
    },
    onError: (error: Error) => showToast('Unable to save context', error.message, 'error'),
  });

  const expireMutation = useMutation({
    mutationFn: expireAITriageContext,
    onSuccess: () => {
      showToast('AI triage context expired', undefined, 'success');
      invalidate();
    },
    onError: (error: Error) => showToast('Unable to expire context', error.message, 'error'),
  });

  const entries = contextQuery.data ?? [];
  const canSave = useMemo(() => {
    const hasScope = form.scopeType === 'GLOBAL' || form.scopeValue.trim().length > 0;
    return !isAuditor && hasScope && form.body.trim().length > 0 && form.expiresAt.length > 0;
  }, [form, isAuditor]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    saveMutation.mutate(buildPayload(form));
  };

  const startEdit = (entry: AITriageContextEntry) => {
    setEditingId(entry.id);
    setForm({
      scopeType: entry.scope.type,
      scopeValue: entry.scope.value ?? '',
      body: entry.body,
      expiresAt: toLocalInputValue(entry.expires_at),
    });
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="container max-w-none flex h-full w-full flex-col gap-6 py-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <BrainCircuit className="h-7 w-7 text-brand-700" />
            <div>
              <h1 className="text-heading-1 font-heading-1 text-default-font">AI Triage Context</h1>
              <p className="text-body text-subtext-color">Shared scoped context applied to matching AI alert triage runs</p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-body text-subtext-color">
            <input
              type="checkbox"
              checked={showExpired}
              onChange={(event) => setShowExpired(event.target.checked)}
            />
            Show expired
          </label>
        </div>

        {!isAuditor && (
          <form className="grid gap-3 rounded-md border border-neutral-border bg-default-background p-4 lg:grid-cols-[180px_1fr_220px_auto]" onSubmit={handleSubmit}>
            <select
              className="h-10 rounded-md border border-neutral-border bg-default-background px-3 text-body"
              value={form.scopeType}
              onChange={(event) => setForm((current) => ({ ...current, scopeType: event.target.value as AITriageContextScopeType, scopeValue: '' }))}
            >
              {SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <input
              className="h-10 rounded-md border border-neutral-border bg-default-background px-3 text-body disabled:bg-neutral-50"
              disabled={form.scopeType === 'GLOBAL'}
              placeholder={form.scopeType === 'GLOBAL' ? 'Applies to all alerts' : 'Scope value'}
              value={form.scopeValue}
              onChange={(event) => setForm((current) => ({ ...current, scopeValue: event.target.value }))}
            />
            <input
              className="h-10 rounded-md border border-neutral-border bg-default-background px-3 text-body"
              type="datetime-local"
              value={form.expiresAt}
              onChange={(event) => setForm((current) => ({ ...current, expiresAt: event.target.value }))}
            />
            <div className="flex gap-2">
              <Button type="submit" icon={<Save />} disabled={!canSave || saveMutation.isPending}>
                {editingId ? 'Save' : 'Create'}
              </Button>
              {editingId && (
                <Button type="button" variant="neutral-secondary" icon={<X />} onClick={resetForm}>
                  Cancel
                </Button>
              )}
            </div>
            <textarea
              className="min-h-24 rounded-md border border-neutral-border bg-default-background px-3 py-2 text-body lg:col-span-4"
              placeholder="Context body"
              value={form.body}
              onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
            />
          </form>
        )}

        <div className="overflow-hidden rounded-md border border-neutral-border bg-default-background">
          <div className="grid grid-cols-[minmax(180px,240px)_1fr_180px_160px] border-b border-neutral-border px-4 py-3 text-caption-bold font-caption-bold text-subtext-color">
            <span>Scope</span>
            <span>Body</span>
            <span>Expiry</span>
            <span>Actions</span>
          </div>
          {contextQuery.isLoading ? (
            <div className="px-4 py-6 text-body text-subtext-color">Loading context</div>
          ) : entries.length === 0 ? (
            <div className="px-4 py-6 text-body text-subtext-color">No context entries</div>
          ) : (
            entries.map((entry) => {
              const expired = Boolean(entry.expired_at) || new Date(entry.expires_at).getTime() <= Date.now();
              return (
                <div key={entry.id} className="grid grid-cols-[minmax(180px,240px)_1fr_180px_160px] gap-4 border-b border-neutral-border px-4 py-3 last:border-b-0">
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="truncate text-body-bold font-body-bold text-default-font">{scopeLabel(entry)}</span>
                    <span className="text-caption text-subtext-color">by {entry.author}</span>
                  </div>
                  <p className="whitespace-pre-wrap text-body text-default-font">{entry.body}</p>
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
                          <Button size="small" variant="destructive-secondary" icon={<X />} onClick={() => expireMutation.mutate(entry.id)}>
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
    </DefaultPageLayout>
  );
}
