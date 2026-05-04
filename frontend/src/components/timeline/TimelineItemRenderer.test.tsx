import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { NoteItem } from '@/types/generated/models/NoteItem';
import type { RecursiveTimelineItem, TimelineItem } from '@/types/timeline';

import { renderWithProviders } from '../../../tests/test-utils';
import { TimelineItemRenderer } from './TimelineItemRenderer';

const mutateMock = vi.fn();

vi.mock('@/hooks/useEnqueueItemEnrichment', () => ({
  useEnqueueItemEnrichment: () => ({
    mutate: mutateMock,
    isPending: false,
    variables: undefined,
  }),
}));

describe('TimelineItemRenderer enrichments', () => {
  beforeEach(() => {
    mutateMock.mockReset();
  });

  it('renders nested replies without duplicating descendant replies', () => {
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'note-parent',
      type: 'note',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      description: 'Parent note',
      replies: {
        'note-reply-1': {
          id: 'note-reply-1',
          type: 'note',
          created_by: 'analyst',
          created_at: '2026-03-14T12:45:11.293811Z',
          timestamp: '2026-03-14T12:45:11.284000Z',
          tags: [],
          flagged: false,
          highlighted: false,
          description: 'First reply',
          replies: {
            'note-reply-2': {
              id: 'note-reply-2',
              type: 'note',
              created_by: 'analyst',
              created_at: '2026-03-14T12:50:11.293811Z',
              timestamp: '2026-03-14T12:50:11.284000Z',
              tags: [],
              flagged: false,
              highlighted: false,
              description: 'Nested reply',
              replies: null,
            },
          },
        },
      },
    };

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="case" />
    );

    expect(screen.getByText('First reply')).toBeInTheDocument();
    expect(screen.getAllByText('Nested reply')).toHaveLength(1);
  });

  it('renders deleted replies as read-only tombstones in original timeline order', () => {
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'note-parent-with-deleted-reply',
      type: 'note',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      description: 'Parent note',
      replies: {
        'late-reply': {
          id: 'late-reply',
          type: 'note',
          created_by: 'analyst',
          created_at: '2026-03-14T12:50:11.293811Z',
          timestamp: '2026-03-14T12:50:11.284000Z',
          tags: [],
          flagged: false,
          highlighted: false,
          description: 'Late reply',
          replies: null,
        },
        'deleted-reply': {
          id: 'deleted-reply',
          type: '_deleted',
          deleted_at: '2026-03-14T13:00:11.293811Z',
          deleted_by: 'admin',
          original_type: 'note',
          original_timestamp: '2026-03-14T12:45:11.284000Z',
          original_created_at: '2026-03-14T12:45:11.293811Z',
          original_created_by: 'analyst',
          parent_id: 'note-parent-with-deleted-reply',
          replies: null,
        },
      },
    };

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        onDelete={vi.fn()}
        onReply={vi.fn()}
      />
    );

    const deletedReply = screen.getByText('deleted note');
    const lateReply = screen.getByText('Late reply');

    expect(deletedReply).toBeInTheDocument();
    expect(lateReply).toBeInTheDocument();
    expect(deletedReply.compareDocumentPosition(lateReply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('continues the parent thread when replying from the final deleted reply', () => {
    const onReply = vi.fn();
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'note-parent-with-final-deleted-reply',
      type: 'note',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      description: 'Parent note',
      replies: {
        'live-reply': {
          id: 'live-reply',
          type: 'note',
          created_by: 'analyst',
          created_at: '2026-03-14T12:45:11.293811Z',
          timestamp: '2026-03-14T12:45:11.284000Z',
          tags: [],
          flagged: false,
          highlighted: false,
          description: 'Live reply',
          replies: null,
        },
        'deleted-final-reply': {
          id: 'deleted-final-reply',
          type: '_deleted',
          deleted_at: '2026-03-14T13:00:11.293811Z',
          deleted_by: 'admin',
          original_type: 'note',
          original_timestamp: '2026-03-14T12:50:11.284000Z',
          original_created_at: '2026-03-14T12:50:11.293811Z',
          original_created_by: 'analyst',
          parent_id: 'note-parent-with-final-deleted-reply',
          replies: null,
        },
      },
    };

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        onDelete={vi.fn()}
        onReply={onReply}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: 'Reply' }).at(-1)!);

    expect(onReply).toHaveBeenCalledWith('note-parent-with-final-deleted-reply');
  });

  it('renders google workspace enrichment content for internal actors', () => {
    const item = {
      id: 'actor-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      name: 'Glenn Bolton',
      title: 'Principal Consultant',
      org: 'Tidemark',
      user_id: 'glenn@glennjamin.com',
      enrichments: {
        google_workspace: {
          phone: '',
          google_id: '101004715095336966229',
          job_title: '',
          suspended: false,
          department: '',
          given_name: 'Glenn',
          family_name: 'Bolton',
          display_name: 'Glenn Bolton',
          organization: '',
          org_unit_path: '/',
          primary_email: 'glenn@glennjamin.com',
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Google Workspace Enrichment')).toBeInTheDocument();
    expect(screen.getAllByText('Glenn Bolton').length).toBeGreaterThan(0);
    expect(screen.getAllByText('glenn@glennjamin.com').length).toBeGreaterThan(0);
    expect(screen.getByText('101004715095336966229')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders description after enrichments for card items', () => {
    const item = {
      id: 'actor-2',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      name: 'Glenn Bolton',
      title: 'Principal Consultant',
      org: 'Tidemark',
      user_id: 'glenn@glennjamin.com',
      description: 'Bottom description',
      enrichments: {
        google_workspace: {
          phone: '',
          google_id: '101004715095336966229',
          job_title: '',
          suspended: false,
          department: '',
          given_name: 'Glenn',
          family_name: 'Bolton',
          display_name: 'Glenn Bolton',
          organization: '',
          org_unit_path: '/',
          primary_email: 'glenn@glennjamin.com',
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    const enrichmentHeading = screen.getByText('Google Workspace Enrichment');
    const description = screen.getByText('Bottom description', { selector: 'p' });

    expect(enrichmentHeading.compareDocumentPosition(description) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders item tags in the shared footer when no description is present', () => {
    const item = {
      id: 'actor-tags-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: ['urgent', 'phishing'],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'alice@example.com',
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByLabelText('Tags')).toBeInTheDocument();
    expect(screen.getByText('urgent')).toBeInTheDocument();
    expect(screen.getByText('phishing')).toBeInTheDocument();
  });

  it('renders linked entity tags in the footer without duplicating metadata tags', () => {
    const item = {
      id: 'linked-alert-tags-1',
      type: 'alert',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      updated_at: '2026-03-14T12:50:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: ['investigate'],
      flagged: false,
      highlighted: false,
      replies: null,
      alert_id: 42,
      title: 'Suspicious login',
      status: 'NEW',
      priority: 'MEDIUM',
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="case" />
    );

    expect(screen.getByLabelText('Tags')).toBeInTheDocument();
    expect(screen.getAllByText('investigate')).toHaveLength(1);
  });

  it('shows the linked source timeline toggle in full timeline cards', () => {
    const item = {
      id: 'linked-alert-source-1',
      type: 'alert',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      updated_at: '2026-03-14T12:50:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      alert_id: 42,
      title: 'Suspicious login',
      status: 'NEW',
      priority: 'MEDIUM',
      source_timeline_items: {
        'source-note-1': {
          id: 'source-note-1',
          type: 'note',
          created_by: 'analyst',
          created_at: '2026-03-14T12:45:11.293811Z',
          timestamp: '2026-03-14T12:45:11.284000Z',
          tags: [],
          flagged: false,
          highlighted: false,
          description: 'Source note',
          replies: null,
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="case" />
    );

    expect(screen.getByText('Show alert timeline (1)')).toBeInTheDocument();
  });

  it('hides the linked source timeline toggle in compact previews', () => {
    const item = {
      id: 'linked-alert-source-compact-1',
      type: 'alert',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      updated_at: '2026-03-14T12:50:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      alert_id: 42,
      title: 'Suspicious login',
      status: 'NEW',
      priority: 'MEDIUM',
      source_timeline_items: {
        'source-note-1': {
          id: 'source-note-1',
          type: 'note',
          created_by: 'analyst',
          created_at: '2026-03-14T12:45:11.293811Z',
          timestamp: '2026-03-14T12:45:11.284000Z',
          tags: [],
          flagged: false,
          highlighted: false,
          description: 'Source note',
          replies: null,
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        compactPreview
      />
    );

    expect(screen.queryByText('Show alert timeline (1)')).not.toBeInTheDocument();
  });

  it('renders multiple provider blocks through the shared enrichment wrapper', () => {
    const item = {
      id: 'observable-1',
      type: 'observable',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      observable_type: 'IP',
      observable_value: '1.1.1.1',
      enrichments: {
        maxmind: {
          results: {
            '1.1.1.1': {
              ip: '1.1.1.1',
              databases: {
                'GeoLite2-ASN': {
                  network: '1.1.1.0/24',
                  autonomous_system_number: 13335,
                  autonomous_system_organization: 'Cloudflare, Inc.',
                },
              },
            },
          },
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('MaxMind Enrichment')).toBeInTheDocument();
    expect(screen.getByText('Cloudflare, Inc.')).toBeInTheDocument();
  });

  it('does not force grouped observable cards to h-full', () => {
    const groupedItems = [
      {
        id: 'observable-1',
        type: 'observable',
        created_by: 'admin',
        created_at: '2026-03-14T12:40:11.293811Z',
        timestamp: '2026-03-14T12:40:11.284000Z',
        tags: [],
        flagged: false,
        highlighted: false,
        replies: null,
        observable_type: 'IP',
        observable_value: '1.1.1.1',
        description: 'First grouped observable',
      },
      {
        id: 'observable-2',
        type: 'observable',
        created_by: 'admin',
        created_at: '2026-03-14T12:40:11.293811Z',
        timestamp: '2026-03-14T12:40:11.284000Z',
        tags: [],
        flagged: false,
        highlighted: false,
        replies: null,
        observable_type: 'DOMAIN',
        observable_value: 'example.com',
        description: 'Second grouped observable',
      },
    ] as TimelineItem[];

    const { container } = renderWithProviders(
      <TimelineItemRenderer
        item={groupedItems[0]}
        items={groupedItems}
        index={0}
        total={2}
        entityId={38}
        entityType="alert"
      />
    );

    const groupedCards = container.querySelectorAll('.group\\/3e384f9c');

    expect(groupedCards.length).toBe(2);
    groupedCards.forEach((card) => {
      expect(card.className).toContain('self-stretch');
      expect(card.className).not.toContain('h-full');
    });
  });

  it('replaces the card primary icon with a spinner while enrichment is active', () => {
    const item = {
      id: 'observable-1',
      type: 'observable',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      observable_type: 'IP',
      observable_value: '1.1.1.1',
      enrichment_status: 'pending',
    } as TimelineItem;

    const { container } = renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    const card = container.querySelector('.group\\/3e384f9c');
    const timelineItem = container.querySelector('#timeline-item-observable-1');

    expect(card).not.toBeNull();
    expect(timelineItem?.querySelector('svg.animate-spin')).not.toBeNull();
  });

  it('renders a refresh enrichment button as the trailing footer action for enrichable items', () => {
    const item = {
      id: 'actor-refresh-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'alice@example.com',
    } as TimelineItem;

    const linkTemplates = [
      {
        id: 'email-link',
        icon: <span>Mail</span>,
        tooltip: 'Email {{user_id}}',
        urlTemplate: 'mailto:{{user_id}}',
        fieldNames: ['user_id'],
      },
    ];

    const { container } = renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="alert"
        linkTemplates={linkTemplates}
      />
    );

    const emailButton = screen.getByRole('button', { name: 'Email alice@example.com' });
    const refreshButton = screen.getByRole('button', { name: /refresh enrichment/i });
    const trailingFooterGroup = container.querySelector('.ml-auto');

    expect(emailButton).toBeInTheDocument();
    expect(refreshButton).toBeInTheDocument();
    expect(trailingFooterGroup).not.toBeNull();
    expect(trailingFooterGroup).toContainElement(refreshButton);
    expect(trailingFooterGroup).not.toContainElement(emailButton);
  });

  it('keeps the refresh enrichment button right-aligned without link template buttons', () => {
    const item = {
      id: 'actor-refresh-only-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'alice@example.com',
    } as TimelineItem;

    const { container } = renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    const refreshButton = screen.getByRole('button', { name: /refresh enrichment/i });
    const rightAlignedFooterGroup = refreshButton.closest('.ml-auto');

    expect(refreshButton).toBeInTheDocument();
    expect(rightAlignedFooterGroup).not.toBeNull();
    expect(rightAlignedFooterGroup).toContainElement(refreshButton);
  });

  it('shows the failed enrichment badge and still uses the refresh button for retryable failures', () => {
    const item = {
      id: 'actor-failed-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'alice@example.com',
      enrichment_status: 'failed',
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Enrichment Failed')).toBeInTheDocument();
    const refreshButton = screen.getByRole('button', { name: /retry enrichment/i });

    expect(refreshButton).toBeInTheDocument();

    fireEvent.click(refreshButton);

    expect(mutateMock).toHaveBeenCalledWith({ itemId: 'actor-failed-1' });
  });
});