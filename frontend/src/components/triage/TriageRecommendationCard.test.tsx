import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../../tests/test-utils';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import { TriageRecommendationCard } from './TriageRecommendationCard';

vi.mock('@/hooks/useCaseRunbooks', () => ({
  useCaseRunbooks: () => ({
    isLoading: false,
    data: {
      items: [
        {
          id: 17,
          human_id: 'RUN-0000017',
          title: 'Replacement Response',
          status: 'PUBLISHED',
          runbook_tasks: [],
        },
      ],
    },
  }),
}));

function pendingEscalationRecommendation(): TriageRecommendationRead {
  return {
    id: 1,
    alert_id: 42,
    disposition: 'NEEDS_INVESTIGATION',
    confidence: 0.82,
    reasoning_bullets: ['Structured response work is appropriate'],
    recommended_actions: [],
    suggested_status: 'ESCALATED',
    request_escalate_to_case: true,
    created_by: 'tidemark_ai',
    created_at: '2026-03-14T12:40:11.293811Z',
    status: 'PENDING',
    applied_context_entries: [],
  };
}

describe('TriageRecommendationCard', () => {
  it('keeps pending escalation recommendation actions as card-level accept and reject buttons', () => {
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={pendingEscalationRecommendation()}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText('Reject').closest('button')).toBeInTheDocument();
    expect(screen.getByText('Accept Recommendation').closest('button')).toBeInTheDocument();
    expect(screen.getByText('Needs Investigation')).toBeVisible();
    expect(screen.queryByText('Pending Review')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escalate to Case \(Reject AI\)/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escalate to Case \(Accept AI\)/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Context included')).not.toBeInTheDocument();
  });

  it('previews reasoning, changes and tasks and expands each row independently', async () => {
    const user = userEvent.setup();
    const onAccept = vi.fn();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          reasoning_bullets: ['Start with the [triage guide](https://example.com).', 'The evidence is incomplete.'],
          recommended_actions: [{ title: 'Pull DNS telemetry' }, 'Compare with the daily baseline'],
          suggested_priority: 'MEDIUM',
          suggested_tags_add: ['dns', 'review'],
          suggested_tags_remove: ['unverified'],
        }}
        onAccept={onAccept}
        onReject={vi.fn()}
      />,
    );

    const reasoning = screen.getByRole('button', { name: /^Reasoning/ });
    const changes = screen.getByRole('button', { name: /^Recommended Changes/ });
    const tasks = screen.getByRole('button', { name: /^Recommended Tasks/ });
    for (const row of [reasoning, changes, tasks]) expect(row).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('82%')).toBeVisible();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(within(reasoning).getByText(/triage guide/)).toBeVisible();
    expect(within(reasoning).queryByRole('link')).not.toBeInTheDocument();
    expect(within(tasks).getByText('Pull DNS telemetry')).toBeVisible();
    expect(within(changes).getByText('+2 tags')).toBeVisible();
    expect(screen.queryByText('The evidence is incomplete.')).not.toBeInTheDocument();
    expect(screen.queryByText('Compare with the daily baseline')).not.toBeInTheDocument();

    reasoning.focus();
    await user.keyboard('{Enter}');
    expect(reasoning).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'triage guide' })).toBeVisible();
    expect(screen.getByText('The evidence is incomplete.')).toBeVisible();
    expect(tasks).toHaveAttribute('aria-expanded', 'false');
    expect(changes).toHaveAttribute('aria-expanded', 'false');

    await user.click(tasks);
    await user.click(changes);
    expect(tasks).toHaveAttribute('aria-expanded', 'true');
    expect(changes).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Compare with the daily baseline')).toBeVisible();
    expect(screen.getByText('unverified')).toBeVisible();

    await user.click(reasoning);
    expect(reasoning).toHaveAttribute('aria-expanded', 'false');
    expect(tasks).toHaveAttribute('aria-expanded', 'true');
    expect(changes).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('button', { name: 'Accept Recommendation' }));
    expect(onAccept).toHaveBeenCalledWith({ apply_status: true, apply_priority: true, apply_assignee: true, apply_tags: true });
  });

  it.each(['PENDING', 'ACCEPTED'] as const)('acknowledges applied context without repeating the entry (%s)', (status) => {
    const contextBody = 'Scheduled maintenance is in progress.';
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          status,
          applied_context_entries: [{ id: 34, body: contextBody, author: 'analyst' }],
        }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText('Context included')).toBeInTheDocument();
    if (status === 'ACCEPTED') expect(screen.getByText('Accepted', { exact: true })).toBeVisible();
    expect(screen.queryByText('Applied Context')).not.toBeInTheDocument();
    expect(screen.queryByText(contextBody)).not.toBeInTheDocument();
  });

  it('offers stale Case Runbook recovery actions after an accept error', async () => {
    const onAccept = vi.fn();

    renderWithProviders(
      <TriageRecommendationCard
        recommendation={pendingEscalationRecommendation()}
        onAccept={onAccept}
        onReject={vi.fn()}
        acceptError="The recommended Case Runbook is no longer published. Choose another published runbook or continue without a runbook."
      />
    );

    expect(screen.getByText('Case Runbook unavailable')).toBeInTheDocument();
    expect(screen.getByText(/continue without a runbook/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Continue Without Runbook/ }));

    expect(onAccept).toHaveBeenCalledWith(expect.objectContaining({
      skip_case_runbook: true,
    }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply Replacement/ })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Apply Replacement/ }));

    expect(onAccept).toHaveBeenCalledWith(expect.objectContaining({
      case_runbook_id: 17,
    }));
  });
});
