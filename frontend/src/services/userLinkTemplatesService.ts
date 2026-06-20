import type {
  LinkTemplateResolveRequest,
  ResolvedLinkTemplateRead,
  UserLinkTemplatePreferenceRead,
  UserLinkTemplatePreferenceUpdate,
} from "@/types/userLinkTemplates";
import type { CancelablePromise } from "@/types/generated/core/CancelablePromise";
import { OpenAPI } from "@/types/generated/core/OpenAPI";
import { request as __request } from "@/types/generated/core/request";

export class UserLinkTemplatesService {
  public static listUserLinkTemplatePreferences(): CancelablePromise<UserLinkTemplatePreferenceRead[]> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/link-templates/user-preferences",
      errors: {
        422: "Validation Error",
      },
    });
  }

  public static upsertUserLinkTemplatePreference({
    templateId,
    requestBody,
  }: {
    templateId: number;
    requestBody: UserLinkTemplatePreferenceUpdate;
  }): CancelablePromise<UserLinkTemplatePreferenceRead> {
    return __request(OpenAPI, {
      method: "PUT",
      url: "/api/v1/link-templates/user-preferences/{template_id}",
      path: {
        template_id: templateId,
      },
      body: requestBody,
      mediaType: "application/json",
      errors: {
        422: "Validation Error",
      },
    });
  }

  public static deleteUserLinkTemplatePreference({
    templateId,
  }: {
    templateId: number;
  }): CancelablePromise<unknown> {
    return __request(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/link-templates/user-preferences/{template_id}",
      path: {
        template_id: templateId,
      },
      errors: {
        422: "Validation Error",
      },
    });
  }

  public static resolveLinkTemplates({
    requestBody,
  }: {
    requestBody: LinkTemplateResolveRequest;
  }): CancelablePromise<ResolvedLinkTemplateRead[]> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/link-templates/resolve",
      body: requestBody,
      mediaType: "application/json",
      errors: {
        422: "Validation Error",
      },
    });
  }
}
