import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TimelineItem } from '@/types/timeline';

import { renderWithProviders } from '../../../tests/test-utils';
import { TimelineItemRenderer } from './TimelineItemRenderer';

describe('TimelineItemRenderer enrichments', () => {
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

    expect(card).not.toBeNull();
    expect(card?.querySelectorAll('.animate-spin')).toHaveLength(1);
  });
});