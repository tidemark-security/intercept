import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '../../../tests/test-utils';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import { TriageRecommendationCard } from './TriageRecommendationCard';

vi.mock('@/hooks/useCaseTemplates', () => ({
  useCaseTemplates: () => ({
    isLoading: false,
    data: {
      items: [
        {
          id: 17,
          human_id: 'TPL-0000017',
          title: 'Replacement Response',
          status: 'PUBLISHED',
          template_tasks: [],
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
  it('offers stale Case Template recovery actions after an accept error', async () => {
    const onAccept = vi.fn();

    renderWithProviders(
      <TriageRecommendationCard
        recommendation={pendingEscalationRecommendation()}
        onAccept={onAccept}
        onReject={vi.fn()}
        acceptError="The recommended Case Template is no longer published. Choose another published template or continue without a template."
      />
    );

    expect(screen.getByText('Case Template unavailable')).toBeInTheDocument();
    expect(screen.getByText(/continue without a template/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Continue Without Template/ }));

    expect(onAccept).toHaveBeenCalledWith(expect.objectContaining({
      skip_case_template: true,
    }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Apply Replacement/ })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /Apply Replacement/ }));

    expect(onAccept).toHaveBeenCalledWith(expect.objectContaining({
      case_template_id: 17,
    }));
  });
});
