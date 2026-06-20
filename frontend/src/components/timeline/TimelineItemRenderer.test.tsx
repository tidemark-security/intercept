import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { NoteItem } from '@/types/generated/models/NoteItem';
import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';
import type { RecursiveTimelineItem, TimelineItem } from '@/types/timeline';

import { renderWithProviders } from '../../../tests/test-utils';
import '@/components/timeline/eventHandlers';
import { TimelineItemRenderer } from './TimelineItemRenderer';
import {
  getLinkedEntityCollapseKey,
  LINKED_ENTITY_COLLAPSE_STORAGE_KEY,
  loadLinkedEntityCollapseState,
  saveLinkedEntityCollapseState,
} from './linkedEntityCollapse';

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
    window.localStorage.clear();
  });

  it('loads and saves linked entity collapse state in localStorage', () => {
    saveLinkedEntityCollapseState({ 'alert:123': true, 'task:TSK-0000042': false }, window.localStorage);

    expect(window.localStorage.getItem(LINKED_ENTITY_COLLAPSE_STORAGE_KEY)).toBe(
      JSON.stringify({ 'alert:123': true, 'task:TSK-0000042': false }),
    );
    expect(loadLinkedEntityCollapseState(window.localStorage)).toEqual({
      'alert:123': true,
      'task:TSK-0000042': false,
    });

    window.localStorage.setItem(LINKED_ENTITY_COLLAPSE_STORAGE_KEY, '{"alert:123":true,"noise":"bad"}');

    expect(loadLinkedEntityCollapseState(window.localStorage)).toEqual({ 'alert:123': true });
  });

  it('renders collapsed linked alert cards with summary fields and without rich details', () => {
    const item = {
      id: 'linked-alert-item',
      type: 'alert',
      alert_id: 123,
      created_by: 'System',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      title: 'Suspicious inbox rule',
      description: 'Long investigation narrative that should be hidden',
      tags: ['mailbox', 'priority-review'],
      flagged: false,
      highlighted: false,
      replies: null,
      priority: 'HIGH',
      status: 'NEW',
      assignee: 'alice',
      source: 'Microsoft Defender',
      enrichments: {
        maxmind: {
          ip: '203.0.113.10',
        },
      },
    } as unknown as TimelineItem;
    const collapseKey = getLinkedEntityCollapseKey(item)!;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        linkedEntityCollapseState={{ [collapseKey]: true }}
        onLinkedEntityCollapseChange={vi.fn()}
      />
    );

    expect(screen.getByText('ALT-0000123')).toBeInTheDocument();
    expect(screen.getByText('Suspicious inbox rule')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Alert' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand Alert Card' })).toBeInTheDocument();
    expect(screen.getByText('Long investigation narrative that should be hidden')).toBeInTheDocument();
    expect(screen.queryByText('mailbox')).not.toBeInTheDocument();
    expect(screen.queryByText('Microsoft Defender')).not.toBeInTheDocument();
    expect(screen.queryByText('MaxMind Enrichment')).not.toBeInTheDocument();
  });

  it('persists per-card linked entity collapse changes', () => {
    const onLinkedEntityCollapseChange = vi.fn();
    const item = {
      id: 'linked-task-item',
      type: 'task',
      task_id: 42,
      task_human_id: 'TSK-0000042',
      created_by: 'System',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      title: 'Contain endpoint',
      description: 'Task description',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      priority: 'MEDIUM',
      status: 'OPEN',
      assignee: 'bob',
    } as unknown as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        linkedEntityCollapseState={{}}
        onLinkedEntityCollapseChange={onLinkedEntityCollapseChange}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Collapse Task Card' }));

    expect(onLinkedEntityCollapseChange).toHaveBeenCalledWith('task:42', true);
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

  it('renders human-authored notes as card-style analyst notes', () => {
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'human-note',
      type: 'note',
      created_by: 'analyst',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      description: 'Human triage note',
      replies: null,
    };

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Analyst note')).toBeInTheDocument();
    expect(screen.getByText('Human')).toBeInTheDocument();
    expect(screen.getByText('Human triage note', { selector: 'p' })).toBeInTheDocument();
  });

  it('renders tagged automation notes with automation treatment', () => {
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'automation-note',
      type: 'note',
      created_by: 'analyst',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: ['status-change'],
      flagged: false,
      highlighted: false,
      description: 'Status changed from NEW to TRIAGED',
      replies: null,
    };

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Automation note')).toBeInTheDocument();
    expect(screen.getByText('Automation')).toBeInTheDocument();
    expect(screen.getByText('status-change')).toBeInTheDocument();
    expect(screen.getByText('Status changed from NEW to TRIAGED', { selector: 'p' })).toBeInTheDocument();
  });

  it('renders generated automation task notes with automation treatment', () => {
    const item: RecursiveTimelineItem<NoteItem> = {
      id: 'automation-task-note',
      type: 'note',
      created_by: 'custom-langflow-agent',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: ['ai-agent', 'automation-completed'],
      flagged: false,
      highlighted: false,
      description: 'Autonomous task completed',
      replies: null,
    };

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Automation note')).toBeInTheDocument();
    expect(screen.getByText('Automation')).toBeInTheDocument();
    expect(screen.getByText('automation-completed')).toBeInTheDocument();
    expect(screen.getByText('Autonomous task completed', { selector: 'p' })).toBeInTheDocument();
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

    const deletedReply = screen.getByText('deleted a note');
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

  it('prioritizes internal actor identity and organization metadata before phone details', () => {
    const item = {
      id: 'actor-priority-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'CORP\\alice',
      contact_phone: '+1-555-0100',
      enrichments: {
        entra_id: {
          display_name: 'Alice Analyst',
          upn: 'alice@example.com',
          sam_account_name: 'alice',
          job_title: 'Security Analyst',
          department: 'SOC',
          office: 'HQ',
          manager_name: 'Morgan Manager',
          account_enabled: true,
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Alice Analyst')).toBeInTheDocument();
    expect(screen.getByText('CORP\\alice')).toBeInTheDocument();
    expect(screen.getByText('Security Analyst')).toBeInTheDocument();
    expect(screen.getByText('SOC')).toBeInTheDocument();
    expect(screen.getByText('Manager')).toBeInTheDocument();
    expect(screen.getByText('Morgan Manager')).toBeInTheDocument();
    expect(screen.getByText('Office / Location')).toBeInTheDocument();
    expect(screen.getByText('HQ')).toBeInTheDocument();

    const manager = screen.getByText('Morgan Manager');
    const phone = screen.getByText('+1-555-0100');

    expect(manager.compareDocumentPosition(phone) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText('Disabled')).not.toBeInTheDocument();
  });

  it('shows disabled as an internal actor characteristic only when explicitly disabled', () => {
    const item = {
      id: 'actor-disabled-1',
      type: 'internal_actor',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      user_id: 'disabled@example.com',
      enrichments: {
        entra_id: {
          display_name: 'Disabled User',
          account_enabled: false,
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Disabled User')).toBeInTheDocument();
    expect(screen.getAllByText('Disabled').length).toBeGreaterThan(0);
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

  it.each([
    {
      type: 'alert',
      entityType: 'case',
      item: {
        alert_id: 42,
        title: 'Suspicious login',
        status: 'NEW',
        priority: 'MEDIUM',
      },
    },
    {
      type: 'case',
      entityType: 'alert',
      item: {
        case_id: 7,
        title: 'Executive phishing cluster',
        status: 'NEW',
        priority: 'HIGH',
      },
    },
    {
      type: 'task',
      entityType: 'case',
      item: {
        task_id: 5,
        task_human_id: 'TSK-0000005',
        title: 'Contain endpoint',
        status: 'OPEN',
        priority: 'LOW',
      },
    },
  ] as const)('renders the linked $type entity markdown description in the rich card', ({ type, entityType, item: entityFields }) => {
    const item = {
      id: `linked-${type}-description-1`,
      type,
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      updated_at: '2026-03-14T12:50:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      description: 'Timeline link note',
      entity_description: 'Underlying **markdown** description',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      assignee: 'alice',
      ...entityFields,
    } as unknown as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType={entityType} />
    );

    expect(screen.getByText('markdown')).toBeInTheDocument();
    expect(screen.getByText('Timeline link note', { selector: 'p' })).toBeInTheDocument();
  });

  it('renders linked source timelines when the linked entity card is expanded', () => {
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
    } as unknown as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="case" />
    );

    expect(screen.getByText('Source note')).toBeInTheDocument();
    expect(screen.queryByText('Show alert timeline (1)')).not.toBeInTheDocument();
    expect(screen.queryByText('Hide alert timeline (1)')).not.toBeInTheDocument();
  });

  it('hides linked source timelines when the linked entity card is collapsed', () => {
    const item = {
      id: 'linked-alert-source-collapsed-1',
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
    } as unknown as TimelineItem;
    const collapseKey = getLinkedEntityCollapseKey(item)!;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        linkedEntityCollapseState={{ [collapseKey]: true }}
        onLinkedEntityCollapseChange={vi.fn()}
      />
    );

    expect(screen.queryByText('Source note')).not.toBeInTheDocument();
    expect(screen.queryByText('Show alert timeline (1)')).not.toBeInTheDocument();
    expect(screen.queryByText('Hide alert timeline (1)')).not.toBeInTheDocument();
  });

  it('hides linked source timelines and the removed hover toggle in compact previews', () => {
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
    } as unknown as TimelineItem;

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
    expect(screen.queryByText('Source note')).not.toBeInTheDocument();
  });

  it('renders attachments in the super-compact variant with filename and graceful incomplete state', () => {
    const item = {
      id: 'attachment-uploading-1',
      type: 'attachment',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      file_name: 'incident-notes.txt',
      mime_type: 'text/plain',
      file_size: 128,
      upload_status: 'UPLOADING',
    } as TimelineItem & AttachmentItem;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        variant="super-compact"
      />
    );

    expect(screen.getByText('incident-notes.txt')).toBeInTheDocument();
    expect(screen.getByText('128.00 B')).toBeInTheDocument();
    expect(screen.queryByText(/Preview unavailable/i)).not.toBeInTheDocument();
  });

  it('renders a tiny attachment preview fallback when super-compact text attachments exceed preview limits', () => {
    const item = {
      id: 'attachment-large-text-1',
      type: 'attachment',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      file_name: 'large-export.json',
      mime_type: 'application/json',
      file_size: 2 * 1024 * 1024,
      upload_status: 'COMPLETE',
    } as TimelineItem & AttachmentItem;

    renderWithProviders(
      <TimelineItemRenderer
        item={item}
        index={0}
        total={1}
        entityId={38}
        entityType="case"
        variant="super-compact"
      />
    );

    expect(screen.getByText('large-export.json')).toBeInTheDocument();
    expect(screen.getByText('Preview unavailable for this text attachment.')).toBeInTheDocument();
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

  it('renders cross-timeline observable correlation matches', () => {
    const item = {
      id: 'observable-correlation-1',
      type: 'observable',
      created_by: 'admin',
      created_at: '2026-03-14T12:40:11.293811Z',
      timestamp: '2026-03-14T12:40:11.284000Z',
      tags: [],
      flagged: false,
      highlighted: false,
      replies: null,
      observable_type: 'IP',
      observable_value: '203.0.113.10',
      enrichments: {
        cross_case_observable: {
          observable_type: 'IP',
          observable_value: '203.0.113.10',
          max_lookback_days: 180,
          match_count: 3,
          matches: [
            {
              entity_type: 'alert',
              entity_id: 12,
              human_id: 'ALT-0000012',
              title: 'Matching alert',
              status: 'NEW',
              priority: 'HIGH',
              updated_at: '2026-03-15T12:00:00Z',
            },
            {
              entity_type: 'case',
              entity_id: 34,
              human_id: 'CAS-0000034',
              title: 'Matching case',
              status: 'OPEN',
              priority: 'MEDIUM',
              updated_at: '2026-03-14T12:00:00Z',
            },
            {
              entity_type: 'task',
              entity_id: 56,
              human_id: 'TSK-0000056',
              title: 'Matching task',
              status: 'TODO',
              priority: 'LOW',
              updated_at: '2026-03-13T12:00:00Z',
            },
          ],
        },
      },
    } as TimelineItem;

    renderWithProviders(
      <TimelineItemRenderer item={item} index={0} total={1} entityId={38} entityType="alert" />
    );

    expect(screen.getByText('Observable Correlation')).toBeInTheDocument();
    expect(screen.getByText('3 matches')).toBeInTheDocument();
    expect(screen.getByText('180d lookback')).toBeInTheDocument();
    expect(screen.getByText('ALT-0000012')).toBeInTheDocument();
    expect(screen.getByText('CAS-0000034')).toBeInTheDocument();
    expect(screen.getByText('TSK-0000056')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /ALT-0000012/i })).toHaveAttribute('href', '/alerts/ALT-0000012');
    expect(screen.getByText('Matching alert')).toBeInTheDocument();
    expect(screen.getByText('Matching case')).toBeInTheDocument();
    expect(screen.getByText('Matching task')).toBeInTheDocument();
    expect(screen.queryByText('alert')).not.toBeInTheDocument();
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
