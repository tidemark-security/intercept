import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '@/types/generated/core/OpenAPI';
import { applyCaseRunbook, listCaseRunbooks } from './caseRunbooksApi';
import { listContextEntries, updateContextEntry } from './contextEntriesApi';
import { ServiceNowAdminApi, type ServiceNowConfigureRequest } from './serviceNowAdminApi';

const originalConfig = { ...OpenAPI };
const serviceNowConfig: ServiceNowConfigureRequest = {
  instance_url: 'https://example.service-now.com',
  username: 'analyst',
  password: '',
  auth_type: 'basic',
  oauth_client_id: '',
  oauth_client_secret: '',
  user_table_enabled: true,
  user_table: 'sys_user',
  user_query_field: 'user_name',
  user_vip_field: 'vip',
  user_privileged_field: 'u_privileged_user',
  cmdb_table_enabled: false,
  cmdb_table: 'cmdb_ci',
  cmdb_query_field: 'name',
  cmdb_criticality_field: 'criticality',
  cmdb_privileged_field: 'u_privileged_system',
  active_only: true,
  ttl_seconds: 86400,
  enabled: true,
};

function mockResponse(body: unknown, status = 200) {
  return vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(function (
    this: XMLHttpRequest,
  ) {
    Object.defineProperties(this, {
      readyState: { value: 4 },
      responseText: { value: JSON.stringify(body) },
      status: { value: status },
    });
    this.dispatchEvent(new ProgressEvent('loadend'));
  });
}

beforeEach(() => {
  OpenAPI.BASE = window.location.origin;
  OpenAPI.WITH_CREDENTIALS = true;
  OpenAPI.CREDENTIALS = 'include';
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.assign(OpenAPI, originalConfig);
  document.cookie = 'XSRF-TOKEN=; Max-Age=0; Path=/';
});

describe('generated API adapters', () => {
  it('sends repeated runbook statuses and normalizes task tags', async () => {
    const open = vi.spyOn(XMLHttpRequest.prototype, 'open');
    mockResponse({
      items: [{ runbook_tasks: [{ title: 'Review alert' }] }],
      total: 1,
      page: 1,
      size: 50,
      pages: 1,
    });

    const result = await listCaseRunbooks(['PUBLISHED', 'DRAFT'], 'host & user');

    const [method, url] = open.mock.calls[0];
    const query = new URL(url).searchParams;
    expect(method).toBe('GET');
    expect(query.getAll('status')).toEqual(['PUBLISHED', 'DRAFT']);
    expect(query.get('search')).toBe('host & user');
    expect(result.items).toEqual([{
      status: 'DRAFT',
      case_tags: [],
      runbook_tasks: [{ title: 'Review alert', tags: [] }],
    }]);
  });

  it('sends a credentialed context edit with the current CSRF cookie', async () => {
    const open = vi.spyOn(XMLHttpRequest.prototype, 'open');
    const setHeader = vi.spyOn(XMLHttpRequest.prototype, 'setRequestHeader');
    document.cookie = 'XSRF-TOKEN=test%2Dtoken; Path=/';
    const body = { body: 'Updated note' };
    const send = mockResponse(body);

    await expect(updateContextEntry(3, body)).resolves.toEqual({ ...body, criteria: [] });

    expect(open).toHaveBeenCalledWith('PUT', expect.stringMatching(/\/context-entries\/3$/), true);
    expect(setHeader).toHaveBeenCalledWith('X-XSRF-TOKEN', 'test-token');
    expect((send.mock.contexts[0] as XMLHttpRequest).withCredentials).toBe(true);
    expect(send).toHaveBeenCalledWith(JSON.stringify(body));
  });

  it('sends runbook task overrides and defaults missing warnings', async () => {
    const open = vi.spyOn(XMLHttpRequest.prototype, 'open');
    const send = mockResponse({ created_task_ids: [6], skipped_task_titles: [] });
    const overrides = [{ index: 0, assignee: 'analyst' }];

    await expect(applyCaseRunbook(3, 5, overrides)).resolves.toEqual({
      created_task_ids: [6],
      skipped_task_titles: [],
      duplicate_warnings: [],
    });

    expect(open).toHaveBeenCalledWith('POST', expect.stringMatching(/\/cases\/3\/apply\/5$/), true);
    expect(send).toHaveBeenCalledWith(JSON.stringify({ task_overrides: overrides }));
  });

  it('preserves ServiceNow preview defaults and supports cancellation', async () => {
    const open = vi.spyOn(XMLHttpRequest.prototype, 'open');
    const result = { provider_id: 'service-now', cache_key: 'analyst' };
    const requestBody = { ...serviceNowConfig, item: { user_id: 'analyst' } };
    const send = mockResponse(result);

    await expect(ServiceNowAdminApi.preview(requestBody)).resolves.toEqual({
      ...result,
      aliases: [],
      enrichment_data: {},
    });
    expect(open).toHaveBeenCalledWith('POST', expect.stringMatching(/\/service-now\/preview$/), true);
    expect(send).toHaveBeenCalledWith(JSON.stringify(requestBody));

    const pending = ServiceNowAdminApi.preview(requestBody);
    const rejection = expect(pending).rejects.toThrow('Request aborted');
    pending.cancel();
    await rejection;
    expect(send).toHaveBeenCalledTimes(1);
  });

  it.each([
    [400, { detail: 'Invalid context' }, 'Invalid context'],
    [403, { detail: { message: 'CSRF validation failed' } }, 'CSRF validation failed'],
    [422, { detail: [{ msg: 'Validation error' }] }, 'Request failed with status 422'],
  ])('preserves the display message for a %s response', async (status, body, message) => {
    mockResponse(body, status);
    await expect(listContextEntries()).rejects.toThrow(message);
  });
});
