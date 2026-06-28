import { fireEvent, screen, waitFor } from '@testing-library/react';
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
