import type { CancelablePromise } from "@/types/generated/core/CancelablePromise";
import { OpenAPI } from "@/types/generated/core/OpenAPI";
import { request as __request } from "@/types/generated/core/request";

export interface ServiceNowConfigureRequest {
  instance_url: string;
  username: string;
  password: string;
  auth_type: "basic" | "oauth_password";
  oauth_client_id: string;
  oauth_client_secret: string;
  user_table: string;
  user_query_field: string;
  user_vip_field: string;
  user_privileged_field: string;
  cmdb_table: string;
  cmdb_query_field: string;
  cmdb_criticality_field: string;
  cmdb_privileged_field: string;
  active_only: boolean;
  ttl_seconds: number;
  enabled: boolean;
}

export interface ServiceNowConfigureResponse {
  instance_url: string;
  settings_saved: number;
  enabled: boolean;
}

export interface ServiceNowPreviewRequest extends ServiceNowConfigureRequest {
  item: Record<string, unknown>;
}

export interface ServiceNowPreviewResponse {
  provider_id: string;
  cache_key: string;
  enrichment_data: Record<string, unknown>;
  aliases: Array<Record<string, unknown>>;
}

export class ServiceNowAdminApi {
  public static configure(
    requestBody: ServiceNowConfigureRequest,
  ): CancelablePromise<ServiceNowConfigureResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/admin/enrichments/service-now/configure",
      body: requestBody,
      mediaType: "application/json",
      errors: {
        422: "Validation Error",
      },
    });
  }

  public static preview(
    requestBody: ServiceNowPreviewRequest,
  ): CancelablePromise<ServiceNowPreviewResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/admin/enrichments/service-now/preview",
      body: requestBody,
      mediaType: "application/json",
      errors: {
        422: "Validation Error",
      },
    });
  }
}
