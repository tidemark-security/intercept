import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
  beforeEach(() => localStorage.removeItem('intercept.alert-detail.triage-recommendation.expansion'));

  it.each([false, true])('keeps the failure detail visible and guards retry while busy (%s)', (isRetrying) => {
    const onRetry = vi.fn();
    const error = 'Retries exhausted: All connection attempts failed';
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{ ...pendingEscalationRecommendation(), status: 'FAILED', error_message: error }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onRetry={onRetry}
        isRetrying={isRetrying}
      />,
    );

    const card = screen.getByRole('region', { name: 'AI Triage Failed' });
    const retry = within(card).getByRole('button', { name: 'Retry' });
    expect(within(card).getByText(error)).toBeVisible();
    expect(within(card).getByText(/look up the alert ID in the triage worker logs/)).toBeVisible();
    expect(retry).toHaveAttribute('aria-busy', String(isRetrying));
    fireEvent.click(retry);
    expect(onRetry).toHaveBeenCalledTimes(isRetrying ? 0 : 1);
  });

  it('keeps an enqueue failure compact and points to the task queue', () => {
    const error = 'Task queue unavailable';
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{ ...pendingEscalationRecommendation(), status: 'FAILED', error_message: error }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        defaultExpanded
      />,
    );

    const card = screen.getByRole('region', { name: 'AI Triage Failed' });
    expect(card).toHaveAttribute('data-layout', 'compact');
    expect(within(card).getByText('Ask an admin to check the task queue for this alert.')).toBeVisible();
    expect(within(card).getByText(error)).toBeVisible();
    expect(within(card).queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers all review actions for a pending recommendation without context', async () => {
    const user = userEvent.setup();
    const onRerun = vi.fn();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={pendingEscalationRecommendation()}
        onRerun={onRerun}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText('Reject').closest('button')).toBeInTheDocument();
    expect(screen.getByText('Accept Recommendation').closest('button')).toBeInTheDocument();
    expect(screen.queryByText('Needs Investigation')).not.toBeInTheDocument();
    expect(screen.getByText('Investigate alert', { exact: true })).toBeVisible();
    expect(screen.queryByText('Pending Review')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escalate to Case \(Reject AI\)/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Escalate to Case \(Accept AI\)/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/context entry supplied/)).not.toBeInTheDocument();
    expect(within(screen.getByRole('group', { name: 'Recommendation preview' })).getByText('1 reason')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Rerun' }));
    expect(onRerun).toHaveBeenCalledWith(pendingEscalationRecommendation().created_at);
  });

  it('shows dismissal in both modes for a benign recommendation with legacy escalation fields', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          disposition: 'BENIGN',
          reasoning_bullets: ['The alert is expected test activity.'],
          recommended_actions: [{ title: 'Investigate the activity' }],
        }}
        defaultExpanded
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText('Dismiss alert')).toBeVisible();
    expect(screen.getByRole('button', { name: /Recommended Changes.*Benign/i })).toBeVisible();
    expect(screen.queryByRole('button', { name: /^Recommended Tasks/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Collapse triage recommendation' }));
    expect(screen.getByText('Dismiss alert')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Accept Recommendation' })).toBeVisible();
  });

  it.each([
    ['dark', 'enabled:border-warning-500'],
    ['light', 'enabled:border-warning-800'],
  ])('matches the page Reject button in the %s theme', async (theme, warningBorder) => {
    localStorage.setItem('intercept.theme-preference', theme);
    const user = userEvent.setup();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={pendingEscalationRecommendation()}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );
    localStorage.removeItem('intercept.theme-preference');

    const pageReject = screen.getByRole('button', { name: 'Reject' });
    await user.click(pageReject);

    const dialog = within(screen.getByRole('dialog'));
    const confirm = dialog.getByRole('button', { name: 'Reject' });
    const cancel = dialog.getByRole('button', { name: /Cancel$/ });
    expect(confirm.className).toBe(pageReject.className);
    expect(confirm).toHaveClass('h-8', warningBorder);
    expect(confirm.querySelector('svg.lucide-x')).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    expect(cancel).toHaveClass('h-8');
    await user.click(cancel);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('summarizes proposed changes in compact mode and keeps the expanded detail rows', async () => {
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

    const summary = screen.getByRole('group', { name: 'Recommendation preview' });
    expect(within(summary).getByText('P3', { ignore: '[aria-hidden="true"]' })).toBeVisible();
    expect(within(summary).getByText('2 reasons').closest('[tabindex="0"]')?.previousElementSibling).toHaveTextContent('P3');
    expect(within(summary).getByText('+2 tags')).toBeVisible();
    expect(within(summary).getByText('−1 tag')).toBeVisible();
    const taskBadge = within(summary).getByText('2 recommended tasks');
    expect(taskBadge).toBeVisible();
    expect(taskBadge.closest('[tabindex="0"]')?.querySelector('svg')).toBeNull();
    expect(screen.queryByText(/triage guide/)).not.toBeInTheDocument();
    expect(screen.queryByText('Pull DNS telemetry')).not.toBeInTheDocument();
    expect(screen.queryByText('unverified')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Expand triage recommendation' }));
    expect(summary).not.toBeInTheDocument();
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
    const removedTag = screen.getByText('unverified');
    expect(removedTag).toBeVisible();
    expect(removedTag.closest('div')?.querySelector('svg.lucide-tag')).toBeInTheDocument();

    await user.click(reasoning);
    expect(reasoning).toHaveAttribute('aria-expanded', 'false');
    expect(tasks).toHaveAttribute('aria-expanded', 'true');
    expect(changes).toHaveAttribute('aria-expanded', 'true');
    await user.click(screen.getByRole('button', { name: 'Accept Recommendation' }));
    expect(onAccept).toHaveBeenCalledWith({ apply_status: true, apply_priority: true, apply_assignee: true, apply_tags: true });
  });

  it('reveals all reasons, task descriptions, and tag names from the compact badges', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          reasoning_bullets: ['Review the **supporting evidence**.', 'The alert needs an owner.'],
          recommended_actions: [{ title: 'Review DNS logs', description: 'Check the documented time window.' }, 'Record the outcome'],
          suggested_tags_add: ['dns', 'review'],
          suggested_tags_remove: ['unverified'],
        }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    for (const [badge, details] of [
      ['2 reasons', ['Review the supporting evidence.', 'The alert needs an owner.']],
      ['2 recommended tasks', ['Review DNS logs', 'Check the documented time window.', 'Record the outcome']],
      ['+2 tags', ['dns', 'review']],
      ['−1 tag', ['unverified']],
    ] as const) {
      const trigger = screen.getByText(badge);
      await user.hover(trigger);
      const tooltip = await screen.findByRole('tooltip');
      details.forEach(detail => expect(tooltip).toHaveTextContent(detail));
      if (badge === '+2 tags' || badge === '−1 tag') {
        expect(tooltip.querySelectorAll('svg.lucide-tag')).toHaveLength(details.length);
      }
      await user.keyboard('{Escape}');
      await waitFor(() => expect(tooltip).not.toBeInTheDocument());
    }
  });

  it.each([undefined, 'The alert needs a different disposition.'])('shows rejection details below the action in both layouts (note: %s)', async (note) => {
    const user = userEvent.setup();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          status: 'REJECTED',
          reviewed_by: 'reviewer@example.test',
          reviewed_at: '2026-03-14T12:45:00Z',
          rejection_category: 'INCORRECT_DISPOSITION',
          rejection_reason: note,
        }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    const card = screen.getByRole('region', { name: 'AI Triage Recommendation' });
    const footer = within(card).getByRole('group', { name: 'Rejection details' });
    const summary = within(card).getByRole('group', { name: 'Triage summary' });
    expect(summary.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(footer).toHaveTextContent('Rejected by reviewer@example.test');
    expect(footer).toHaveTextContent('Incorrect Disposition');
    if (note) expect(footer).toHaveTextContent(note);
    expect(screen.getAllByText('reviewer@example.test')).toHaveLength(1);
    expect(within(card).queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument();

    await user.click(within(card).getByRole('button', { name: 'Expand triage recommendation' }));
    const details = within(card).getByRole('group', { name: 'Triage details' });
    expect(details.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(footer).toBeVisible();
  });

  it.each(['PENDING', 'ACCEPTED', 'REJECTED'] as const)('shows supplied context and offers a rerun only while pending (%s)', async (status) => {
    const user = userEvent.setup();
    const contextBody = 'Scheduled maintenance is in progress.';
    const secondContextBody = 'Maintenance covers the staging network.';
    const onRerun = vi.fn();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          status,
          ...(status === 'ACCEPTED' && {
            reviewed_by: 'reviewer@example.test',
            reviewed_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          }),
          context_snapshot_verified: true,
          applied_context_entries: [
            { id: 34, body: contextBody, author: 'analyst' },
            { id: 35, body: secondContextBody, author: 'analyst' },
          ],
        }}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onRerun={onRerun}
      />,
    );

    expect(screen.getByText('2 context entries supplied')).toBeVisible();
    if (status === 'ACCEPTED') {
      expect(screen.getByText('Accepted', { exact: true })).toBeVisible();
      const footer = screen.getByRole('group', { name: 'Acceptance details' });
      const summary = screen.getByRole('group', { name: 'Triage summary' });
      expect(summary.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(footer).toHaveTextContent('Accepted by reviewer@example.test · 5 minutes ago');
      expect(screen.getAllByText('reviewer@example.test')).toHaveLength(1);
    }
    expect(screen.queryByText(contextBody)).not.toBeInTheDocument();
    if (status === 'PENDING') {
      await user.click(screen.getByRole('button', { name: 'Rerun' }));
      expect(onRerun).toHaveBeenCalledWith(pendingEscalationRecommendation().created_at);
    } else {
      expect(screen.queryByRole('button', { name: 'Rerun' })).not.toBeInTheDocument();
    }
    await user.click(screen.getByRole('button', { name: 'Expand triage recommendation' }));
    if (status === 'ACCEPTED') {
      expect(screen.getByRole('group', { name: 'Acceptance details' })).toBeVisible();
    }
    const contextAtTriage = screen.getByRole('button', { name: /^Context at Triage/ });
    expect(within(contextAtTriage).getByText(contextBody)).toBeVisible();
    expect(screen.queryByText(secondContextBody)).not.toBeInTheDocument();
    await user.click(contextAtTriage);
    expect(screen.getByText(contextBody)).toBeVisible();
    expect(screen.getByText(secondContextBody)).toBeVisible();
  });

  it('labels legacy saved entries as unverified and offers a rerun when context is now available', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <TriageRecommendationCard
        recommendation={{
          ...pendingEscalationRecommendation(),
          applied_context_entries: [{ id: 34, body: 'Unverified context', author: 'analyst' }],
        }}
        hasCurrentContext
        defaultExpanded
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onRerun={vi.fn()}
      />,
    );
    const savedContext = screen.getByRole('button', { name: /^Saved Context/ });
    expect(within(savedContext).getByText('Context for this run is unverified')).toBeVisible();
    expect(within(savedContext).getByText('Unverified context', { exact: true })).toBeVisible();
    expect(savedContext).toHaveTextContent(/Context for this run is unverified.*View saved entries/);
    expect(screen.getByRole('button', { name: 'Rerun' })).toBeVisible();
    expect(screen.queryByText('1 context entry supplied')).not.toBeInTheDocument();
    await user.click(savedContext);
    const [notice, entry] = screen.getAllByRole('listitem');
    expect(notice).toHaveTextContent('Context for this run is unverified');
    expect(within(entry).getByText('Unverified context')).toBeVisible();
    expect(within(entry).getByText('analyst')).toBeVisible();
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
