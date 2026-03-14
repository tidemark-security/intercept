import React, { useState, useEffect, useMemo, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { AdminPageLayout } from "../components/layout/AdminPageLayout";
import { TextField } from "@/components/forms/TextField";
import { TextArea } from "@/components/forms/TextArea";
import { Button } from "@/components/buttons/Button";
import { Switch } from "@/components/forms/Switch";
import { TagsManager } from "@/components/forms/TagsManager";
import { useTheme } from "@/contexts/ThemeContext";
import { useToast } from "@/contexts/ToastContext";
import { cn } from "@/utils/cn";

import { useSession } from "../contexts/sessionContext";
import { ApiError } from "../types/generated/core/ApiError";
import { AdminService } from "../types/generated/services/AdminService";
import { AuthenticationService } from "../types/generated/services/AuthenticationService";
import { LangflowService } from "../types/generated/services/LangflowService";
import type {
  AppSettingRead,
  MaxMindConfigureResponse,
  MaxMindDatabaseStatus,
} from "../types/generated";
import type { SettingType } from "../types/generated/models/SettingType";
import {
  useSettings,
  useUpdateSetting,
  useCreateSetting,
} from "../hooks/useSettings";

import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  FileText,
  Globe2,
  Lock,
  RefreshCw,
  Save,
  Settings,
  Sparkles,
  Upload,
} from "lucide-react";

const DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS = [
  "Resolved",
  "False Positive",
  "True Positive",
  "Escalated",
  "No Action Required",
  "Duplicate",
];

const MAXMIND_DATABASES_QUERY_KEY = ["admin", "maxmind", "databases"] as const;

const parseTagsValue = (value: string): string[] => {
  const trimmedValue = value.trim();
  if (!trimmedValue) {
    return [];
  }

  if (trimmedValue.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmedValue);
      if (Array.isArray(parsed)) {
        const parsedTags: string[] = [];
        const seenTags = new Set<string>();

        parsed.forEach((tag) => {
          if (typeof tag !== "string") {
            return;
          }
          const normalizedTag = tag.trim();
          if (!normalizedTag) {
            return;
          }
          const loweredTag = normalizedTag.toLowerCase();
          if (seenTags.has(loweredTag)) {
            return;
          }
          seenTags.add(loweredTag);
          parsedTags.push(normalizedTag);
        });

        return parsedTags;
      }
    } catch {
      // Fall back to legacy comma-separated parsing.
    }
  }

  const parsedTags: string[] = [];
  const seenTags = new Set<string>();

  value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
    .forEach((tag) => {
      const normalizedTag = tag.toLowerCase();
      if (seenTags.has(normalizedTag)) {
        return;
      }
      seenTags.add(normalizedTag);
      parsedTags.push(tag);
    });

  return parsedTags;
};

const parseBooleanValue = (value: string): boolean => {
  const normalized = value.trim().toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on";
};

const extractApiErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof ApiError) {
    if (err.body && typeof err.body === "object" && "detail" in err.body) {
      const detail = (err.body as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (
        detail &&
        typeof detail === "object" &&
        "message" in detail &&
        typeof (detail as { message?: unknown }).message === "string"
      ) {
        return (detail as { message: string }).message;
      }
    }
    if (err.body && typeof err.body === "object" && "message" in err.body) {
      const message = (err.body as { message?: unknown }).message;
      if (typeof message === "string") {
        return message;
      }
    }
  }

  if (err instanceof Error && err.message) {
    return err.message;
  }

  return fallback;
};

function AdminSettings() {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const { user: currentUser } = useSession();
  const {
    data: settings = [],
    isLoading: loading,
    error: queryError,
  } = useSettings();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const updateMutation = useUpdateSetting();
  const createMutation = useCreateSetting();
  const geoipConfFileInputRef = useRef<HTMLInputElement>(null);

  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [testingOidcDiscovery, setTestingOidcDiscovery] = useState(false);
  const [oidcDiscoveryStatus, setOidcDiscoveryStatus] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [geoipConfText, setGeoipConfText] = useState("");
  const [isMaxMindDragging, setIsMaxMindDragging] = useState(false);
  const [maxMindConfigureStatus, setMaxMindConfigureStatus] = useState<{
    variant: StatusVariant;
    title: string;
    description: string;
  } | null>(null);
  const [maxMindUpdateStatus, setMaxMindUpdateStatus] = useState<{
    variant: StatusVariant;
    title: string;
    description: string;
  } | null>(null);

  const isAdmin = currentUser?.role === "ADMIN";

  const {
    data: maxMindDatabases = [],
    isLoading: maxMindDatabasesLoading,
  } = useQuery({
    queryKey: MAXMIND_DATABASES_QUERY_KEY,
    queryFn: () => AdminService.getMaxmindDatabaseStatusApiV1AdminEnrichmentsMaxmindDatabasesGet(),
    enabled: isAdmin,
    staleTime: 30_000,
  });

  const maxMindConfigureMutation = useMutation({
    mutationFn: (confText: string) =>
      AdminService.configureMaxmindApiV1AdminEnrichmentsMaxmindConfigurePost({
        requestBody: { conf_text: confText },
      }),
    onSuccess: async (response: MaxMindConfigureResponse) => {
      setMaxMindConfigureStatus({
        variant: "success",
        title: "GeoIP.conf imported",
        description: `Saved ${response.settings_saved ?? 0} settings and queued initial download${response.task_id ? ` (${response.task_id})` : ""}.`,
      });
      setGeoipConfText("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin", "settings"] }),
        queryClient.invalidateQueries({ queryKey: MAXMIND_DATABASES_QUERY_KEY }),
      ]);
    },
    onError: (err) => {
      setMaxMindConfigureStatus({
        variant: "error",
        title: "GeoIP.conf import failed",
        description: extractApiErrorMessage(err, "Failed to import GeoIP.conf"),
      });
    },
  });

  const maxMindUpdateMutation = useMutation({
    mutationFn: () => AdminService.triggerMaxmindUpdateApiV1AdminEnrichmentsMaxmindUpdatePost(),
    onSuccess: async (response: { task_id?: string | null }) => {
      setMaxMindUpdateStatus({
        variant: "success",
        title: "Update queued",
        description: `Worker queued a MaxMind database refresh${response?.task_id ? ` (${response.task_id})` : ""}.`,
      });
      await queryClient.invalidateQueries({ queryKey: MAXMIND_DATABASES_QUERY_KEY });
    },
    onError: (err) => {
      setMaxMindUpdateStatus({
        variant: "error",
        title: "Failed to queue update",
        description: extractApiErrorMessage(err, "Failed to queue MaxMind update"),
      });
    },
  });

  // Surface React Query errors
  useEffect(() => {
    if (queryError) {
      showToast(
        "Failed to load settings",
        extractApiErrorMessage(queryError, "Failed to load settings"),
        "error",
      );
    }
  }, [queryError, showToast]);

  const updateSetting = async (key: string, value: string) => {
    try {
      await updateMutation.mutateAsync({ key, value });
      showToast("Setting updated", key, "success");
    } catch (err) {
      showToast(
        "Failed to update setting",
        extractApiErrorMessage(err, "Failed to update setting"),
        "error",
      );
    }
  };

  const createSetting = async (
    key: string,
    value: string,
    isSecret: boolean,
    category?: string,
    valueType?: SettingType,
  ) => {
    try {
      const derivedCategory = category || key.split(".")[0] || "general";
      await createMutation.mutateAsync({
        key,
        value,
        value_type: valueType || "STRING",
        is_secret: isSecret,
        category: derivedCategory,
        description: "",
      });
      showToast("Setting created", key, "success");
    } catch (err) {
      showToast(
        "Failed to create setting",
        extractApiErrorMessage(err, "Failed to create setting"),
        "error",
      );
    }
  };

  const testConnection = async () => {
    try {
      setTestingConnection(true);
      setConnectionStatus(null);

      const data =
        await LangflowService.testLangflowConnectionApiV1LangflowTestConnectionPost();
      setConnectionStatus(data);
    } catch (err) {
      setConnectionStatus({
        success: false,
        message: err instanceof Error ? err.message : "Connection test failed",
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const testOidcDiscovery = async () => {
    try {
      setTestingOidcDiscovery(true);
      setOidcDiscoveryStatus(null);

      const data =
        await AuthenticationService.testOidcDiscoveryApiV1AuthOidcTestDiscoveryGet();
      setOidcDiscoveryStatus(data);
    } catch (err) {
      setOidcDiscoveryStatus({
        success: false,
        message: extractApiErrorMessage(err, "OIDC discovery test failed"),
      });
    } finally {
      setTestingOidcDiscovery(false);
    }
  };

  const handleSaveSetting = (
    key: string,
    value: string,
    isSecret: boolean = false,
    valueType?: SettingType,
  ) => {
    const existingSetting = settings.find((s) => s.key === key);
    if (existingSetting && existingSetting.id > 0) {
      updateSetting(key, value);
    } else {
      createSetting(key, value, isSecret, undefined, valueType);
    }
  };

  const submitGeoIpConf = () => {
    const trimmed = geoipConfText.trim();
    if (!trimmed) {
      setMaxMindConfigureStatus({
        variant: "warning",
        title: "GeoIP.conf required",
        description: "Paste a GeoIP.conf file or drop one into the import area before saving.",
      });
      return;
    }
    setMaxMindConfigureStatus(null);
    maxMindConfigureMutation.mutate(trimmed);
  };

  const loadGeoIpConfFile = (file: File | null) => {
    if (!file) {
      return;
    }
    file.text()
      .then((text) => {
        setGeoipConfText(text);
        setMaxMindConfigureStatus({
          variant: "success",
          title: "GeoIP.conf loaded",
          description: `${file.name} is ready to import. Review the contents below and save when ready.`,
        });
      })
      .catch((err: unknown) => {
        setMaxMindConfigureStatus({
          variant: "error",
          title: "Failed to read file",
          description: extractApiErrorMessage(err, "Failed to read the selected GeoIP.conf file"),
        });
      });
  };

  const formatFileSize = (value?: number | null) => {
    if (!value || value <= 0) {
      return "-";
    }
    if (value < 1024) {
      return `${value} B`;
    }
    if (value < 1024 * 1024) {
      return `${(value / 1024).toFixed(1)} KB`;
    }
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatTimestamp = (value?: string | null) => {
    if (!value) {
      return "-";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "-";
    }
    return parsed.toLocaleString();
  };

  const maxMindConfigured =
    Boolean(getSetting("enrichment.maxmind.account_id")) &&
    Boolean(getSetting("enrichment.maxmind.license_key"));

  // Keys rendered in custom sections above — excluded from the generic Advanced section
  const CUSTOM_KEYS = new Set([
    "langflow.base_url",
    "langflow.api_key",
    "langflow.default_flow_id",
    "langflow.alert_triage_flow_id",
    "langflow.case_detail_flow_id",
    "langflow.task_detail_flow_id",
    "langflow.timeout",
    "triage.auto_enqueue",
    "case_closure.recommended_tags",
    "oidc.enabled",
    "oidc.discovery_url",
    "oidc.client_id",
    "oidc.client_secret",
    "oidc.scopes",
    "oidc.provider_name",
    "oidc.jit_provisioning",
    "oidc.default_role",
    "oidc.role_claim_path",
    "oidc.role_mapping",
    "oidc.sso_bypass_users",
    "enrichment.maxmind.enabled",
    "enrichment.maxmind.account_id",
    "enrichment.maxmind.license_key",
    "enrichment.maxmind.edition_ids",
    "enrichment.maxmind.update_frequency_hours",
    "enrichment.maxmind.ttl_seconds",
  ]);

  // Group remaining settings by category for the Advanced section
  const advancedByCategory = useMemo(() => {
    const grouped: Record<string, AppSettingRead[]> = {};
    for (const s of settings) {
      if (CUSTOM_KEYS.has(s.key)) continue;
      const cat = s.category || "general";
      (grouped[cat] ??= []).push(s);
    }
    // Sort categories alphabetically, but put "bootstrap" last
    return Object.entries(grouped).sort(([a], [b]) => {
      if (a === "bootstrap") return 1;
      if (b === "bootstrap") return -1;
      return a.localeCompare(b);
    });
  }, [settings]);

  if (!isAdmin) {
    return (
      <DefaultPageLayout withContainer>
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4">
          <AlertCircle className="text-[48px] text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to access settings
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  const getSetting = (key: string): string => {
    const setting = settings.find((s) => s.key === key);
    return setting?.value || "";
  };

  /** Pull value + registry metadata for a setting key */
  const settingMeta = (key: string) => {
    const s = settings.find((s) => s.key === key);
    const localOnly = !!s?.local_only;
    const envOverride = s?.source === "env";
    const readOnly = localOnly || envOverride;
    return {
      value: s?.value || "",
      description: s?.description || "",
      source: s?.source,
      localOnly,
      envOverride,
      readOnly,
    };
  };

  return (
    <AdminPageLayout
      title="Configuration Settings"
      subtitle="Manage system integrations and preferences"
    >
      <div className="flex h-full w-full flex-col gap-6">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <span className="text-body text-subtext-color">
              Loading settings...
            </span>
          </div>
        ) : (
          <div className="flex flex-col gap-8">
            {/* LangFlow Settings Section */}
            <section className="flex flex-col gap-6 rounded-lg border border-neutral-border bg-default-background p-6">
              <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                <Settings className="text-[20px] text-subtext-color" />
                <h2 className="text-heading-3 font-heading-3 text-default-font">
                  LangFlow Settings
                </h2>
              </div>

              {/* LangFlow API Base URL */}
              <SettingField
                label="LangFlow API Base URL"
                {...settingMeta("langflow.base_url")}
                onSave={(value) =>
                  handleSaveSetting("langflow.base_url", value)
                }
                placeholder="http://langflow/api/v1"
              />

              {/* API Key */}
              <SettingField
                label="API Key"
                {...settingMeta("langflow.api_key")}
                onSave={(value) =>
                  handleSaveSetting("langflow.api_key", value, true)
                }
                placeholder="sk-..."
                isSecret
              />

              {/* Default Flow ID */}
              <SettingField
                label="Default Flow ID"
                {...settingMeta("langflow.default_flow_id")}
                onSave={(value) =>
                  handleSaveSetting("langflow.default_flow_id", value)
                }
                placeholder="flow-123"
              />

              {/* Alert Triage Flow ID */}
              <SettingField
                label="Alert Triage Flow ID"
                {...settingMeta("langflow.alert_triage_flow_id")}
                onSave={(value) =>
                  handleSaveSetting("langflow.alert_triage_flow_id", value)
                }
                placeholder="flow-456"
              />

              {/* Case Detail Flow ID */}
              <SettingField
                label="Case Detail Flow ID"
                {...settingMeta("langflow.case_detail_flow_id")}
                onSave={(value) =>
                  handleSaveSetting("langflow.case_detail_flow_id", value)
                }
                placeholder="flow-789"
              />

              {/* Task Detail Flow ID */}
              <SettingField
                label="Task Detail Flow ID"
                {...settingMeta("langflow.task_detail_flow_id")}
                onSave={(value) =>
                  handleSaveSetting("langflow.task_detail_flow_id", value)
                }
                placeholder="flow-abc"
              />

              {/* Timeout */}
              <SettingField
                label="Request Timeout (seconds)"
                {...settingMeta("langflow.timeout")}
                onSave={(value) => handleSaveSetting("langflow.timeout", value)}
                placeholder="30"
              />

              {/* Test Connection */}
              <div className="flex flex-col gap-2 border-t border-neutral-border pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-body-bold font-body-bold text-default-font">
                      Test Connection
                    </span>
                    <p className="text-caption font-caption text-subtext-color">
                      Verify LangFlow is reachable with current settings
                    </p>
                  </div>
                  <Button
                    variant="neutral-tertiary"
                    onClick={testConnection}
                    disabled={testingConnection}
                  >
                    {testingConnection ? "Testing..." : "Test Connection"}
                  </Button>
                </div>
                {connectionStatus && (
                  <StatusCallout
                    variant={connectionStatus.success ? "success" : "error"}
                    title={
                      connectionStatus.success
                        ? "Connectivity test passed"
                        : "Connectivity test failed"
                    }
                    description={connectionStatus.message}
                    isDarkTheme={isDarkTheme}
                  />
                )}
              </div>
            </section>

            {/* AI Triage Settings Section */}
            <section className="flex flex-col gap-6 rounded-lg border border-neutral-border bg-default-background p-6">
              <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                <Sparkles className="text-[20px] text-subtext-color" />
                <h2 className="text-heading-3 font-heading-3 text-default-font">
                  AI Triage Settings
                </h2>
              </div>

              {/* Triage Feature Status */}

              <div className="flex flex-col gap-1">
                <label className="text-body-bold font-body-bold text-default-font">AI-Assisted Alert Triage</label>
                <p className="text-caption font-caption text-subtext-color">
                  Allow AI to analyse new alerts and suggest triage actions.
                </p>
                              <StatusCallout
                variant={
                  getSetting("langflow.alert_triage_flow_id")
                    ? "success"
                    : "warning"
                }
                title={
                  getSetting("langflow.alert_triage_flow_id")
                    ? "AI Triage is enabled"
                    : "AI Triage is disabled"
                }
                description={
                  getSetting("langflow.alert_triage_flow_id")
                    ? "Alert Triage Flow ID is configured."
                    : "Set Alert Triage Flow ID above to enable AI triage."
                }
                isDarkTheme={isDarkTheme}
              />
              </div>



              {/* Auto-enqueue Setting */}
              <BooleanSettingField
                label="Auto-enqueue on Alert Creation"
                description={settingMeta("triage.auto_enqueue").description}
                source={settingMeta("triage.auto_enqueue").source}
                readOnly={settingMeta("triage.auto_enqueue").readOnly}
                value={parseBooleanValue(getSetting("triage.auto_enqueue"))}
                onSave={(value) =>
                  handleSaveSetting(
                    "triage.auto_enqueue",
                    value ? "true" : "false",
                    false,
                    "BOOLEAN",
                  )
                }
                disabled={!getSetting("langflow.alert_triage_flow_id")}
              />
            </section>

            <section className="flex flex-col gap-6 rounded-lg border border-neutral-border bg-default-background p-6">
              <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                <Settings className="text-[20px] text-subtext-color" />
                <h2 className="text-heading-3 font-heading-3 text-default-font">
                  Case Closure Settings
                </h2>
              </div>

              <TagsSettingField
                label="Recommended Closure Tags"
                description={
                  settingMeta("case_closure.recommended_tags").description
                }
                source={settingMeta("case_closure.recommended_tags").source}
                readOnly={settingMeta("case_closure.recommended_tags").readOnly}
                value={getSetting("case_closure.recommended_tags")}
                fallbackTags={DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS}
                onSave={(tags) =>
                  handleSaveSetting(
                    "case_closure.recommended_tags",
                    JSON.stringify(tags),
                    false,
                    "JSON",
                  )
                }
              />
            </section>

            <section className="flex flex-col gap-6 rounded-lg border border-neutral-border bg-default-background p-6">
              <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                <Settings className="text-[20px] text-subtext-color" />
                <h2 className="text-heading-3 font-heading-3 text-default-font">
                  OIDC / Single Sign-On
                </h2>
              </div>

              <StatusCallout
                variant={
                  parseBooleanValue(getSetting("oidc.enabled"))
                    ? getSetting("oidc.discovery_url") && getSetting("oidc.client_id")
                      ? "success"
                      : "warning"
                    : "warning"
                }
                title={
                  parseBooleanValue(getSetting("oidc.enabled"))
                    ? "OIDC is enabled"
                    : "OIDC is disabled"
                }
                description={
                  parseBooleanValue(getSetting("oidc.enabled"))
                    ? "OIDC sign-in swaps the external token for the app's normal session cookie."
                    : "Enable OIDC to route sign-in through your external identity provider."
                }
                isDarkTheme={isDarkTheme}
              />

              <BooleanSettingField
                label="Enable OIDC"
                description={settingMeta("oidc.enabled").description}
                source={settingMeta("oidc.enabled").source}
                readOnly={settingMeta("oidc.enabled").readOnly}
                value={parseBooleanValue(getSetting("oidc.enabled"))}
                onSave={(value) =>
                  handleSaveSetting(
                    "oidc.enabled",
                    value ? "true" : "false",
                    false,
                    "BOOLEAN",
                  )
                }
              />

              <SettingField
                label="Discovery URL"
                {...settingMeta("oidc.discovery_url")}
                onSave={(value) => handleSaveSetting("oidc.discovery_url", value)}
                placeholder="https://idp.example.com/.well-known/openid-configuration"
              />

              <SettingField
                label="Client ID"
                {...settingMeta("oidc.client_id")}
                onSave={(value) => handleSaveSetting("oidc.client_id", value)}
                placeholder="intercept-backend"
              />

              <SettingField
                label="Client Secret"
                {...settingMeta("oidc.client_secret")}
                onSave={(value) => handleSaveSetting("oidc.client_secret", value, true)}
                placeholder="Client secret"
                isSecret
              />

              <SettingField
                label="Scopes"
                {...settingMeta("oidc.scopes")}
                onSave={(value) => handleSaveSetting("oidc.scopes", value)}
                placeholder="openid email profile"
              />

              <SettingField
                label="Provider Name"
                {...settingMeta("oidc.provider_name")}
                onSave={(value) => handleSaveSetting("oidc.provider_name", value)}
                placeholder="SSO"
              />

              <BooleanSettingField
                label="Just-In-Time Provisioning"
                description={settingMeta("oidc.jit_provisioning").description}
                source={settingMeta("oidc.jit_provisioning").source}
                readOnly={settingMeta("oidc.jit_provisioning").readOnly}
                value={parseBooleanValue(getSetting("oidc.jit_provisioning"))}
                onSave={(value) =>
                  handleSaveSetting(
                    "oidc.jit_provisioning",
                    value ? "true" : "false",
                    false,
                    "BOOLEAN",
                  )
                }
              />

              <SettingField
                label="Default Role"
                {...settingMeta("oidc.default_role")}
                onSave={(value) => handleSaveSetting("oidc.default_role", value)}
                placeholder="ANALYST"
              />

              <SettingField
                label="Role Claim Path"
                {...settingMeta("oidc.role_claim_path")}
                onSave={(value) => handleSaveSetting("oidc.role_claim_path", value)}
                placeholder="realm_access.roles"
              />

              <SettingField
                label="Role Mapping JSON"
                {...settingMeta("oidc.role_mapping")}
                onSave={(value) => handleSaveSetting("oidc.role_mapping", value, false, "JSON")}
                placeholder='{"idp-admins":"ADMIN","idp-auditors":"AUDITOR"}'
              />

              <TagsSettingField
                label="Password Login Bypass Users"
                description={`${settingMeta("oidc.sso_bypass_users").description} Admin users are always allowed.`}
                source={settingMeta("oidc.sso_bypass_users").source}
                readOnly={settingMeta("oidc.sso_bypass_users").readOnly}
                value={getSetting("oidc.sso_bypass_users")}
                onSave={(tags) =>
                  handleSaveSetting(
                    "oidc.sso_bypass_users",
                    JSON.stringify(tags),
                    false,
                    "JSON",
                  )
                }
              />

              <div className="flex flex-col gap-2 border-t border-neutral-border pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-body-bold font-body-bold text-default-font">
                      Test Discovery
                    </span>
                    <p className="text-caption font-caption text-subtext-color">
                      Validate the provider discovery document and required endpoints.
                    </p>
                  </div>
                  <Button
                    variant="neutral-tertiary"
                    onClick={testOidcDiscovery}
                    disabled={testingOidcDiscovery}
                  >
                    {testingOidcDiscovery ? "Testing..." : "Test Discovery"}
                  </Button>
                </div>
                {oidcDiscoveryStatus && (
                  <StatusCallout
                    variant={oidcDiscoveryStatus.success ? "success" : "error"}
                    title={
                      oidcDiscoveryStatus.success
                        ? "OIDC discovery succeeded"
                        : "OIDC discovery failed"
                    }
                    description={oidcDiscoveryStatus.message}
                    isDarkTheme={isDarkTheme}
                  />
                )}
              </div>
            </section>

            <section className="flex flex-col gap-6 rounded-lg border border-neutral-border bg-default-background p-6">
              <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                <Globe2 className="text-[20px] text-subtext-color" />
                <h2 className="text-heading-3 font-heading-3 text-default-font">
                  MaxMind GeoIP
                </h2>
              </div>

              <StatusCallout
                variant={maxMindConfigured ? "success" : "warning"}
                title={maxMindConfigured ? "MaxMind is configured" : "MaxMind is not configured"}
                description={
                  maxMindConfigured
                    ? "Workers will use MMDB databases stored in blob storage for IP enrichment."
                    : "Import a GeoIP.conf file or populate the MaxMind settings below to enable database downloads."
                }
                isDarkTheme={isDarkTheme}
              />

              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <span className="text-body-bold font-body-bold text-default-font">
                      GeoIP.conf Import
                    </span>
                    <p className="text-caption font-caption text-subtext-color">
                      Drop a GeoIP.conf file here, select one from disk, or paste its contents below to preconfigure MaxMind downloads.
                    </p>
                  </div>
                  <input
                    ref={geoipConfFileInputRef}
                    type="file"
                    accept=".conf,text/plain"
                    className="hidden"
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                      loadGeoIpConfFile(event.target.files?.[0] ?? null);
                      event.target.value = "";
                    }}
                  />
                  <Button
                    variant="neutral-tertiary"
                    onClick={() => geoipConfFileInputRef.current?.click()}
                    icon={<FileText className="text-[16px]" />}
                  >
                    Choose File
                  </Button>
                </div>

                <div
                  className={cn(
                    "flex min-h-[120px] cursor-pointer flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed px-6 py-8 transition-colors",
                    isMaxMindDragging
                      ? "border-focus-border bg-neutral-100"
                      : "border-neutral-border bg-default-background hover:border-neutral-400"
                  )}
                  onClick={() => geoipConfFileInputRef.current?.click()}
                  onDragOver={(event: React.DragEvent<HTMLDivElement>) => {
                    event.preventDefault();
                    setIsMaxMindDragging(true);
                  }}
                  onDragLeave={(event: React.DragEvent<HTMLDivElement>) => {
                    event.preventDefault();
                    setIsMaxMindDragging(false);
                  }}
                  onDrop={(event: React.DragEvent<HTMLDivElement>) => {
                    event.preventDefault();
                    setIsMaxMindDragging(false);
                    loadGeoIpConfFile(event.dataTransfer.files?.[0] ?? null);
                  }}
                >
                  <Upload className="text-[24px] text-subtext-color" />
                  <div className="flex flex-col items-center gap-1 text-center">
                    <span className="text-body-bold font-body-bold text-default-font">
                      Drop GeoIP.conf here
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      The file contents will be parsed and saved into the MaxMind admin settings.
                    </span>
                  </div>
                </div>

                <TextArea
                  label="GeoIP.conf contents"
                  helpText="Paste the file contents exactly as provided by MaxMind. The import saves AccountID, LicenseKey, and EditionIDs."
                >
                  <TextArea.Input
                    value={geoipConfText}
                    onChange={(event: React.ChangeEvent<HTMLTextAreaElement>) => {
                      setGeoipConfText(event.target.value);
                    }}
                    placeholder="# Paste GeoIP.conf here"
                  />
                </TextArea>

                <div className="flex items-center gap-3">
                  <Button
                    variant="brand-primary"
                    onClick={submitGeoIpConf}
                    disabled={maxMindConfigureMutation.isPending}
                    icon={<Save className="text-[16px]" />}
                  >
                    {maxMindConfigureMutation.isPending ? "Importing..." : "Import GeoIP.conf"}
                  </Button>
                  <Button
                    variant="neutral-secondary"
                    onClick={() => setGeoipConfText("")}
                    disabled={maxMindConfigureMutation.isPending || !geoipConfText.trim()}
                  >
                    Clear
                  </Button>
                </div>

                {maxMindConfigureStatus && (
                  <StatusCallout
                    variant={maxMindConfigureStatus.variant}
                    title={maxMindConfigureStatus.title}
                    description={maxMindConfigureStatus.description}
                    isDarkTheme={isDarkTheme}
                  />
                )}
              </div>

              <BooleanSettingField
                label="Enable MaxMind Enrichment"
                description={settingMeta("enrichment.maxmind.enabled").description}
                source={settingMeta("enrichment.maxmind.enabled").source}
                readOnly={settingMeta("enrichment.maxmind.enabled").readOnly}
                value={parseBooleanValue(getSetting("enrichment.maxmind.enabled"))}
                onSave={(value) =>
                  handleSaveSetting(
                    "enrichment.maxmind.enabled",
                    value ? "true" : "false",
                    false,
                    "BOOLEAN",
                  )
                }
              />

              <SettingField
                label="Account ID"
                {...settingMeta("enrichment.maxmind.account_id")}
                onSave={(value) => handleSaveSetting("enrichment.maxmind.account_id", value)}
                placeholder="1313424"
              />

              <SettingField
                label="License Key"
                {...settingMeta("enrichment.maxmind.license_key")}
                onSave={(value) => handleSaveSetting("enrichment.maxmind.license_key", value, true)}
                placeholder="License key"
                isSecret
              />

              <TagsSettingField
                label="Edition IDs"
                description={settingMeta("enrichment.maxmind.edition_ids").description}
                source={settingMeta("enrichment.maxmind.edition_ids").source}
                readOnly={settingMeta("enrichment.maxmind.edition_ids").readOnly}
                value={getSetting("enrichment.maxmind.edition_ids")}
                onSave={(tags) =>
                  handleSaveSetting(
                    "enrichment.maxmind.edition_ids",
                    JSON.stringify(tags),
                    false,
                    "JSON",
                  )
                }
              />

              <SettingField
                label="Update Frequency (hours)"
                {...settingMeta("enrichment.maxmind.update_frequency_hours")}
                onSave={(value) => handleSaveSetting("enrichment.maxmind.update_frequency_hours", value, false, "NUMBER")}
                placeholder="24"
              />

              <SettingField
                label="Enrichment TTL (seconds)"
                {...settingMeta("enrichment.maxmind.ttl_seconds")}
                onSave={(value) => handleSaveSetting("enrichment.maxmind.ttl_seconds", value, false, "NUMBER")}
                placeholder="604800"
              />

              <div className="flex flex-col gap-4 border-t border-neutral-border pt-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <span className="text-body-bold font-body-bold text-default-font">
                      Database Status
                    </span>
                    <p className="text-caption font-caption text-subtext-color">
                      Shows which MMDB editions are present in blob storage and currently loaded on this node.
                    </p>
                  </div>
                  <Button
                    variant="neutral-tertiary"
                    onClick={() => maxMindUpdateMutation.mutate()}
                    disabled={maxMindUpdateMutation.isPending || !maxMindConfigured}
                    icon={<RefreshCw className={cn("text-[16px]", maxMindUpdateMutation.isPending && "animate-spin")} />}
                  >
                    {maxMindUpdateMutation.isPending ? "Queueing..." : "Check for Updates"}
                  </Button>
                </div>

                {maxMindUpdateStatus && (
                  <StatusCallout
                    variant={maxMindUpdateStatus.variant}
                    title={maxMindUpdateStatus.title}
                    description={maxMindUpdateStatus.description}
                    isDarkTheme={isDarkTheme}
                  />
                )}

                <div className="overflow-x-auto rounded-md border border-neutral-border">
                  <table className="min-w-full divide-y divide-neutral-border">
                    <thead className="bg-neutral-50">
                      <tr>
                        <th className="px-4 py-3 text-left text-caption-bold font-caption-bold text-default-font">Edition</th>
                        <th className="px-4 py-3 text-left text-caption-bold font-caption-bold text-default-font">Storage</th>
                        <th className="px-4 py-3 text-left text-caption-bold font-caption-bold text-default-font">Loaded</th>
                        <th className="px-4 py-3 text-left text-caption-bold font-caption-bold text-default-font">Size</th>
                        <th className="px-4 py-3 text-left text-caption-bold font-caption-bold text-default-font">Last Updated</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-neutral-border bg-default-background">
                      {maxMindDatabasesLoading ? (
                        <tr>
                          <td colSpan={5} className="px-4 py-6 text-body text-subtext-color">
                            Loading database status...
                          </td>
                        </tr>
                      ) : maxMindDatabases.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="px-4 py-6 text-body text-subtext-color">
                            No MaxMind editions configured yet.
                          </td>
                        </tr>
                      ) : (
                        maxMindDatabases.map((database: MaxMindDatabaseStatus) => (
                          <tr key={database.edition_id}>
                            <td className="px-4 py-3 text-body text-default-font">{database.edition_id}</td>
                            <td className="px-4 py-3 text-body text-default-font">
                              <StatusPill active={!!database.available_in_storage} activeLabel="Stored" inactiveLabel="Missing" />
                            </td>
                            <td className="px-4 py-3 text-body text-default-font">
                              <StatusPill active={!!database.loaded} activeLabel="Loaded" inactiveLabel="Idle" />
                            </td>
                            <td className="px-4 py-3 text-body text-subtext-color">{formatFileSize(database.file_size_bytes)}</td>
                            <td className="px-4 py-3 text-body text-subtext-color">{formatTimestamp(database.last_updated)}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>

            {/* Advanced Settings — auto-generated from registry */}
            {advancedByCategory.length > 0 && (
              <section className="flex flex-col gap-4 rounded-lg border border-neutral-border bg-default-background p-6">
                <div className="flex items-center gap-2 border-b border-neutral-border pb-4">
                  <Settings className="text-[20px] text-subtext-color" />
                  <h2 className="text-heading-3 font-heading-3 text-default-font">
                    Advanced Settings
                  </h2>
                </div>

                {advancedByCategory.map(([category, catSettings]) => (
                  <AdvancedCategorySection
                    key={category}
                    category={category}
                    settings={catSettings}
                    onSave={(key, value) => handleSaveSetting(key, value)}
                  />
                ))}
              </section>
            )}
          </div>
        )}
      </div>
    </AdminPageLayout>
  );
}

interface SettingFieldProps {
  label: string;
  description: string;
  value: string;
  onSave: (value: string) => void;
  placeholder?: string;
  isSecret?: boolean;
  source?: string;
  localOnly?: boolean;
  envOverride?: boolean;
  readOnly?: boolean;
}

type StatusVariant = "success" | "error" | "warning";

function getStatusVariantVisuals(variant: StatusVariant, isDarkTheme: boolean) {
  if (variant === "success") {
    return {
      icon: CheckCircle,
      containerClass: isDarkTheme
        ? "border-success-500 bg-success-1000"
        : "border-success-600 bg-success-50",
      iconClass: isDarkTheme ? "text-success-500" : "text-success-800",
      titleClass: isDarkTheme ? "text-success-500" : "text-success-900",
      descriptionClass: isDarkTheme ? "text-success-400" : "text-success-900",
    };
  }

  if (variant === "error") {
    return {
      icon: AlertCircle,
      containerClass: isDarkTheme
        ? "border-error-500 bg-error-1000"
        : "border-error-200 bg-error-50",
      iconClass: isDarkTheme ? "text-error-500" : "text-error-800",
      titleClass: isDarkTheme ? "text-error-500" : "text-error-900",
      descriptionClass: isDarkTheme ? "text-error-400" : "text-error-800",
    };
  }

  return {
    icon: AlertCircle,
    containerClass: isDarkTheme
      ? "border-warning-500 bg-warning-1000"
      : "border-warning-200 bg-warning-50",
    iconClass: isDarkTheme ? "text-warning-500" : "text-warning-800",
    titleClass: isDarkTheme ? "text-warning-500" : "text-warning-900",
    descriptionClass: isDarkTheme ? "text-warning-400" : "text-warning-800",
  };
}

interface StatusCalloutProps {
  variant: StatusVariant;
  title: string;
  description?: string;
  isDarkTheme: boolean;
}

function StatusCallout({
  variant,
  title,
  description,
  isDarkTheme,
}: StatusCalloutProps) {
  const {
    icon: Icon,
    containerClass,
    iconClass,
    titleClass,
    descriptionClass,
  } = getStatusVariantVisuals(variant, isDarkTheme);

  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-md border p-3",
        containerClass,
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4", iconClass)} />
        <span className={cn("text-body-bold font-body-bold", titleClass)}>
          {title}
        </span>
      </div>
      {description && (
        <p className={cn("text-caption font-caption", descriptionClass)}>
          {description}
        </p>
      )}
    </div>
  );
}

function SettingField({
  label,
  description,
  value,
  onSave,
  placeholder,
  isSecret = false,
  source,
  localOnly = false,
  envOverride = false,
  readOnly = false,
}: SettingFieldProps) {
  const [editedValue, setEditedValue] = useState(value);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    if (!isEditing) {
      setEditedValue(value);
    }
  }, [value, isEditing]);

  const handleSave = () => {
    onSave(editedValue);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditedValue(value);
    setIsEditing(false);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <label className="text-body-bold font-body-bold text-default-font">
          {label}
        </label>
        {source && (
          <SourceBadge
            source={source}
            localOnly={localOnly}
            envOverride={envOverride}
          />
        )}
      </div>
      <p className="text-caption font-caption text-subtext-color">
        {description}
      </p>
      <div className="flex items-center gap-2">
        <TextField className="flex-1" disabled={readOnly}>
          <TextField.Input
            value={editedValue}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setEditedValue(e.target.value);
              setIsEditing(true);
            }}
            placeholder={placeholder}
            type={isSecret && !isEditing ? "password" : "text"}
            disabled={readOnly}
          />
        </TextField>
        {isEditing && !readOnly && (
          <div className="flex gap-2">
            <Button
              variant="brand-primary"
              size="small"
              onClick={handleSave}
              className="w-24 justify-center whitespace-nowrap"
              icon={<Save className="text-[16px]" />}
            >
              Save
            </Button>
            <Button
              variant="neutral-secondary"
              size="small"
              onClick={handleCancel}
              className="w-24 justify-center whitespace-nowrap"
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

interface TagsSettingFieldProps {
  label: string;
  description: string;
  value: string;
  fallbackTags?: string[];
  onSave: (tags: string[]) => void;
  source?: string;
  localOnly?: boolean;
  envOverride?: boolean;
  readOnly?: boolean;
}

function TagsSettingField({
  label,
  description,
  value,
  fallbackTags = [],
  onSave,
  source,
  localOnly = false,
  envOverride = false,
  readOnly = false,
}: TagsSettingFieldProps) {
  const [editedTags, setEditedTags] = useState<string[]>([]);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    if (!isEditing) {
      const parsedTags = parseTagsValue(value);
      setEditedTags(parsedTags.length > 0 ? parsedTags : fallbackTags);
    }
  }, [value, fallbackTags, isEditing]);

  const handleSave = () => {
    onSave(editedTags);
    setIsEditing(false);
  };

  const handleCancel = () => {
    const parsedTags = parseTagsValue(value);
    setEditedTags(parsedTags.length > 0 ? parsedTags : fallbackTags);
    setIsEditing(false);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <label className="text-body-bold font-body-bold text-default-font">
          {label}
        </label>
        {source && (
          <SourceBadge
            source={source}
            localOnly={localOnly}
            envOverride={envOverride}
          />
        )}
      </div>
      <p className="text-caption font-caption text-subtext-color">
        {description}
      </p>
      <TagsManager
        tags={editedTags}
        onTagsChange={(tags) => {
          if (!readOnly) {
            setEditedTags(tags);
            setIsEditing(true);
          }
        }}
        label=""
        placeholder="Enter tags and press Enter"
      />
      {isEditing && !readOnly && (
        <div className="flex gap-2">
          <Button
            variant="brand-primary"
            size="small"
            onClick={handleSave}
            className="w-24 justify-center whitespace-nowrap"
            icon={<Save className="text-[16px]" />}
          >
            Save
          </Button>
          <Button
            variant="neutral-secondary"
            size="small"
            onClick={handleCancel}
            className="w-24 justify-center whitespace-nowrap"
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}

interface BooleanSettingFieldProps {
  label: string;
  description: string;
  value: boolean;
  onSave: (value: boolean) => void;
  disabled?: boolean;
  source?: string;
  localOnly?: boolean;
  envOverride?: boolean;
  readOnly?: boolean;
}

function BooleanSettingField({
  label,
  description,
  value,
  onSave,
  disabled = false,
  source,
  localOnly = false,
  envOverride = false,
  readOnly = false,
}: BooleanSettingFieldProps) {
  const isDisabled = disabled || readOnly;

  const handleChange = (checked: boolean) => {
    if (!isDisabled) onSave(checked);
  };

  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <label
            className={`text-body-bold font-body-bold ${isDisabled ? "text-subtext-color" : "text-default-font"}`}
          >
            {label}
          </label>
          {source && (
            <SourceBadge
              source={source}
              localOnly={localOnly}
              envOverride={envOverride}
            />
          )}
        </div>
        <p className="text-caption font-caption text-subtext-color">
          {description}
        </p>
      </div>
      <Switch
        checked={value}
        onCheckedChange={handleChange}
        disabled={isDisabled}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Source badge — shows where the current value comes from
// ---------------------------------------------------------------------------

function SourceBadge({
  source,
  localOnly,
  envOverride,
}: {
  source?: string;
  localOnly?: boolean;
  envOverride?: boolean;
}) {
  const label = source || "default";
  const showLock = !!localOnly || !!envOverride;
  const lockTitle = localOnly
    ? "Read-only - this setting is local-only and must be set via environment variable or .env file, otherwise the default applies."
    : envOverride
      ? "Read-only - this setting is currently overridden by an environment variable."
      : undefined;
  const colors: Record<string, string> = {
    env: "bg-blue-100 text-blue-800",
    database: "bg-green-100 text-green-800",
    default: "bg-neutral-100 text-neutral-600",
  };

  return (
    <span className="flex items-center gap-1">
      <span
        className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium leading-tight ${colors[label] ?? colors.default}`}
      >
        {label}
      </span>
      {showLock && (
        <span title={lockTitle}>
          <Lock className="h-3 w-3 text-subtext-color" />
        </span>
      )}
    </span>
  );
}

function StatusPill({
  active,
  activeLabel,
  inactiveLabel,
}: {
  active: boolean;
  activeLabel: string;
  inactiveLabel: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium leading-tight",
        active ? "bg-success-50 text-success-900" : "bg-neutral-100 text-neutral-600"
      )}
    >
      {active ? activeLabel : inactiveLabel}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Collapsible category group for Advanced Settings
// ---------------------------------------------------------------------------

interface AdvancedCategorySectionProps {
  category: string;
  settings: AppSettingRead[];
  onSave: (key: string, value: string) => void;
}

function AdvancedCategorySection({
  category,
  settings: catSettings,
  onSave,
}: AdvancedCategorySectionProps) {
  const [open, setOpen] = useState(false);
  const displayName = category.charAt(0).toUpperCase() + category.slice(1);

  return (
    <div className="border-b border-neutral-border last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 py-3 text-left text-body-bold font-body-bold text-default-font hover:text-brand-primary transition-colors"
      >
        {open ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronRight className="h-4 w-4" />
        )}
        {displayName}
        <span className="ml-auto text-caption text-subtext-color">
          {catSettings.length} settings
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-3 pb-4 pl-6">
          {catSettings.map((s) => (
            <AdvancedSettingRow key={s.key} setting={s} onSave={onSave} />
          ))}
        </div>
      )}
    </div>
  );
}

function AdvancedSettingRow({
  setting,
  onSave,
}: {
  setting: AppSettingRead;
  onSave: (key: string, value: string) => void;
}) {
  const [editedValue, setEditedValue] = useState(setting.value || "");
  const [editing, setEditing] = useState(false);
  const localOnly = !!setting.local_only;
  const envOverride = setting.source === "env";
  const readOnly = localOnly || envOverride;

  useEffect(() => {
    if (!editing) {
      setEditedValue(setting.value || "");
    }
  }, [setting.value, editing]);

  const handleSave = () => {
    onSave(setting.key, editedValue);
    setEditing(false);
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-caption-bold text-default-font font-mono">
          {setting.key}
        </span>
        <SourceBadge
          source={setting.source}
          localOnly={localOnly}
          envOverride={envOverride}
        />
      </div>
      {setting.description && (
        <p className="text-caption text-subtext-color">{setting.description}</p>
      )}
      <div className="flex items-center gap-2">
        <TextField className="flex-1" disabled={readOnly}>
          <TextField.Input
            value={editedValue}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setEditedValue(e.target.value);
              setEditing(true);
            }}
            type={setting.is_secret ? "password" : "text"}
            disabled={readOnly}
          />
        </TextField>
        {editing && !readOnly && (
          <div className="flex gap-2">
            <Button
              variant="brand-primary"
              size="small"
              onClick={handleSave}
              className="w-24 justify-center whitespace-nowrap"
              icon={<Save className="text-[16px]" />}
            >
              Save
            </Button>
            <Button
              variant="neutral-secondary"
              size="small"
              className="w-24 justify-center whitespace-nowrap"
              onClick={() => {
                setEditedValue(setting.value || "");
                setEditing(false);
              }}
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminSettings;
