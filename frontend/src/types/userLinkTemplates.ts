export type UserLinkTemplatePreferenceUpdate = {
  enabled: boolean;
  values: Record<string, string>;
};

export type UserLinkTemplatePreferenceRead = UserLinkTemplatePreferenceUpdate & {
  id: number;
  user_id: string;
  template_id: number;
  created_at: string;
  updated_at: string;
};

export type LinkTemplateResolveRequest = {
  item: Record<string, unknown>;
};

export type ResolvedLinkTemplateRead = {
  id: number;
  template_id: string;
  name: string;
  icon_name: string;
  tooltip: string;
  url: string;
  display_order: number;
};
