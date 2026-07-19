export const OPEN_GLOBAL_SEARCH_EVENT = 'intercept:open-global-search';

export interface OpenGlobalSearchDetail {
  query?: string;
  tags?: string[];
}

export function openGlobalSearch(detail: OpenGlobalSearchDetail = {}) {
  window.dispatchEvent(new CustomEvent<OpenGlobalSearchDetail>(OPEN_GLOBAL_SEARCH_EVENT, { detail }));
}
