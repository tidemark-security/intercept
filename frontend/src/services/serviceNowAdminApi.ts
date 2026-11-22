import { CancelablePromise } from '@/types/generated/core/CancelablePromise';
import type { ServiceNowConfigureRequest as ApiServiceNowConfigureRequest } from '@/types/generated/models/ServiceNowConfigureRequest';
import type { ServiceNowConfigureResponse as ApiServiceNowConfigureResponse } from '@/types/generated/models/ServiceNowConfigureResponse';
import type { ServiceNowPreviewResponse as ApiServiceNowPreviewResponse } from '@/types/generated/models/ServiceNowPreviewResponse';
import { AdminService } from '@/types/generated/services/AdminService';

export type ServiceNowConfigureResponse = Required<ApiServiceNowConfigureResponse>;

export type ServiceNowConfigureRequest = Omit<Required<ApiServiceNowConfigureRequest>, 'auth_type'> & {
  auth_type: 'basic' | 'oauth_password';
};

export type ServiceNowPreviewRequest = ServiceNowConfigureRequest & {
  item: Record<string, unknown>;
};

export type ServiceNowPreviewResponse = Pick<ApiServiceNowPreviewResponse, 'provider_id' | 'cache_key'> & {
  enrichment_data: Record<string, unknown>;
  aliases: Record<string, unknown>[];
};

function mapCancelableResponse<T, U>(request: CancelablePromise<T>, transform: (response: T) => U): CancelablePromise<U> {
  return new CancelablePromise((resolve, reject, onCancel) => {
    onCancel(() => request.cancel());
    void request.then((response) => resolve(transform(response))).catch(reject);
  });
}

export class ServiceNowAdminApi {
  public static configure(requestBody: ServiceNowConfigureRequest): CancelablePromise<ServiceNowConfigureResponse> {
    const request = AdminService.configureServiceNowApiV1AdminEnrichmentsServiceNowConfigurePost({ requestBody });
    return mapCancelableResponse(request, (response) => ({
      ...response,
      settings_saved: response.settings_saved ?? 0,
      enabled: response.enabled ?? true,
    }));
  }

  public static preview(requestBody: ServiceNowPreviewRequest): CancelablePromise<ServiceNowPreviewResponse> {
    const request = AdminService.previewServiceNowApiV1AdminEnrichmentsServiceNowPreviewPost({ requestBody });
    return mapCancelableResponse(request, (response) => ({
      ...response,
      enrichment_data: response.enrichment_data ?? {},
      aliases: response.aliases ?? [],
    }));
  }
}
