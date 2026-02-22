import React, { useState, useEffect } from "react";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { AdminPageLayout } from "../components/layout/AdminPageLayout";
import { TextField } from "@/components/forms/TextField";
import { Button } from "@/components/buttons/Button";
import { Toast } from "@/components/feedback/Toast";
import { Switch } from "@/components/forms/Switch";
import { TagsManager } from "@/components/forms/TagsManager";

import { useSession } from "../contexts/sessionContext";
import { AdminService } from "../types/generated/services/AdminService";
import { LangflowService } from "../types/generated/services/LangflowService";
import type { AppSettingRead } from "../types/generated";
import type { SettingType } from "../types/generated/models/SettingType";

import { AlertCircle, CheckCircle, Save, Settings, Sparkles } from 'lucide-react';

const DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS = [
  "Resolved",
  "False Positive",
  "True Positive",
  "Escalated",
  "No Action Required",
  "Duplicate",
];

const parseCommaSeparatedTags = (value: string): string[] => {
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

function AdminSettings() {
  const { user: currentUser } = useSession();
  const [settings, setSettings] = useState<AppSettingRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<{ success: boolean; message: string } | null>(null);

  const isAdmin = currentUser?.role === "ADMIN";

  const loadSettings = async () => {
    try {
      setLoading(true);
      // Load all settings (not just langflow category)
      const data = await AdminService.getAllSettingsApiV1AdminSettingsGet({});
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const updateSetting = async (key: string, value: string) => {
    try {
      await AdminService.updateSettingApiV1AdminSettingsKeyPut({
        key,
        requestBody: { value, description: null },
      });

      setSuccess(`Updated ${key}`);
      setTimeout(() => setSuccess(null), 3000);
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update setting");
      setTimeout(() => setError(null), 5000);
    }
  };

  const createSetting = async (key: string, value: string, isSecret: boolean, category?: string, valueType?: SettingType) => {
    try {
      // Derive category from key prefix if not provided (e.g., "langflow.base_url" -> "langflow")
      const derivedCategory = category || key.split('.')[0] || 'general';
      
      await AdminService.createSettingApiV1AdminSettingsPost({
        requestBody: {
          key,
          value,
          value_type: valueType || "STRING",
          is_secret: isSecret,
          category: derivedCategory,
          description: "",
        },
      });

      setSuccess(`Created ${key}`);
      setTimeout(() => setSuccess(null), 3000);
      await loadSettings();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create setting");
      setTimeout(() => setError(null), 5000);
    }
  };

  const testConnection = async () => {
    try {
      setTestingConnection(true);
      setConnectionStatus(null);

      const data = await LangflowService.testLangflowConnectionApiV1LangflowTestConnectionPost();
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

  useEffect(() => {
    if (isAdmin) {
      loadSettings();
    }
  }, [isAdmin]);

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

  const handleSaveSetting = (key: string, value: string, isSecret: boolean = false, valueType?: SettingType) => {
    const existingSetting = settings.find((s) => s.key === key);
    if (existingSetting) {
      updateSetting(key, value);
    } else {
      createSetting(key, value, isSecret, undefined, valueType);
    }
  };

  return (
    <AdminPageLayout title="Configuration Settings" subtitle="Manage system integrations and preferences">
      <div className="flex h-full w-full flex-col gap-6">
        {/* Error/Success Toasts */}
        {error && (
          <Toast
            variant="error"
            icon={<AlertCircle />}
            title={error}
          />
        )}
        {success && (
          <Toast
            variant="success"
            icon={<CheckCircle />}
            title={success}
          />
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <span className="text-body text-subtext-color">Loading settings...</span>
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
                description="The base URL of your LangFlow instance"
                value={getSetting("langflow.base_url")}
                onSave={(value) => handleSaveSetting("langflow.base_url", value)}
                placeholder="http://langflow/api/v1"
              />

              {/* API Key */}
              <SettingField
                label="API Key"
                description="Authentication key for LangFlow (will be encrypted)"
                value={getSetting("langflow.api_key")}
                onSave={(value) => handleSaveSetting("langflow.api_key", value, true)}
                placeholder="sk-..."
                isSecret
              />

              {/* Default Flow ID */}
              <SettingField
                label="Default Flow ID"
                description="The default LangFlow flow to use for general chat"
                value={getSetting("langflow.default_flow_id")}
                onSave={(value) => handleSaveSetting("langflow.default_flow_id", value)}
                placeholder="flow-123"
              />

              {/* Alert Triage Flow ID */}
              <SettingField
                label="Alert Triage Flow ID"
                description="The LangFlow flow to use for alert triage assistance"
                value={getSetting("langflow.alert_triage_flow_id")}
                onSave={(value) => handleSaveSetting("langflow.alert_triage_flow_id", value)}
                placeholder="flow-456"
              />

              {/* Case Detail Flow ID */}
              <SettingField
                label="Case Detail Flow ID"
                description="The LangFlow flow to use for case detail assistance"
                value={getSetting("langflow.case_detail_flow_id")}
                onSave={(value) => handleSaveSetting("langflow.case_detail_flow_id", value)}
                placeholder="flow-789"
              />

              {/* Task Detail Flow ID */}
              <SettingField
                label="Task Detail Flow ID"
                description="The LangFlow flow to use for task detail assistance"
                value={getSetting("langflow.task_detail_flow_id")}
                onSave={(value) => handleSaveSetting("langflow.task_detail_flow_id", value)}
                placeholder="flow-abc"
              />

              {/* Timeout */}
              <SettingField
                label="Request Timeout (seconds)"
                description="Maximum time to wait for LangFlow responses"
                value={getSetting("langflow.timeout") || "30"}
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
                  <div
                    className={`rounded p-3 ${
                      connectionStatus.success
                        ? "bg-success-50 text-success-900"
                        : "bg-error-50 text-error-900"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {connectionStatus.success ? (
                        <CheckCircle className="text-[16px]" />
                      ) : (
                        <AlertCircle className="text-[16px]" />
                      )}
                      <span className="text-body-bold font-body-bold">
                        {connectionStatus.message}
                      </span>
                    </div>
                  </div>
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
              <div className="flex flex-col gap-2 rounded-md bg-neutral-50 p-4">
                <span className="text-caption-bold font-caption-bold text-default-font">
                  Feature Status
                </span>
                <div className="flex items-center gap-2">
                  {getSetting("langflow.alert_triage_flow_id") ? (
                    <>
                      <CheckCircle className="h-4 w-4 text-success-600" />
                      <span className="text-body font-body text-success-700">
                        AI Triage is enabled (Alert Triage Flow ID is configured)
                      </span>
                    </>
                  ) : (
                    <>
                      <AlertCircle className="h-4 w-4 text-warning-600" />
                      <span className="text-body font-body text-warning-700">
                        AI Triage is disabled (set Alert Triage Flow ID above to enable)
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Auto-enqueue Setting */}
              <BooleanSettingField
                label="Auto-enqueue on Alert Creation"
                description="Automatically queue alerts for AI triage when they are created. When disabled, users can manually request AI triage from the alert detail view."
                value={getSetting("triage.auto_enqueue") !== "false"}
                onSave={(value) => handleSaveSetting("triage.auto_enqueue", value ? "true" : "false", false, "BOOLEAN")}
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
                description="Suggested tags shown in the case closure modal. Users can still add custom tags."
                value={getSetting("case_closure.recommended_tags")}
                fallbackTags={DEFAULT_CASE_CLOSURE_RECOMMENDED_TAGS}
                onSave={(tags) => handleSaveSetting("case_closure.recommended_tags", tags.join(", "), false, "STRING")}
              />
            </section>
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
}

function SettingField({
  label,
  description,
  value,
  onSave,
  placeholder,
  isSecret = false,
}: SettingFieldProps) {
  const [editedValue, setEditedValue] = useState(value);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setEditedValue(value);
  }, [value]);

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
      <label className="text-body-bold font-body-bold text-default-font">
        {label}
      </label>
      <p className="text-caption font-caption text-subtext-color">{description}</p>
      <div className="flex items-center gap-2">
        <TextField className="flex-1">
          <TextField.Input
            value={editedValue}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
              setEditedValue(e.target.value);
              setIsEditing(true);
            }}
            placeholder={placeholder}
            type={isSecret && !isEditing ? "password" : "text"}
          />
        </TextField>
        {isEditing && (
          <div className="flex gap-2">
            <Button variant="brand-primary" size="small" onClick={handleSave}>
              <Save className="text-[16px]" />
              Save
            </Button>
            <Button variant="neutral-secondary" size="small" onClick={handleCancel}>
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
}

function TagsSettingField({
  label,
  description,
  value,
  fallbackTags = [],
  onSave,
}: TagsSettingFieldProps) {
  const [editedTags, setEditedTags] = useState<string[]>([]);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    const parsedTags = parseCommaSeparatedTags(value);
    setEditedTags(parsedTags.length > 0 ? parsedTags : fallbackTags);
    setIsEditing(false);
  }, [value, fallbackTags]);

  const handleSave = () => {
    onSave(editedTags);
    setIsEditing(false);
  };

  const handleCancel = () => {
    const parsedTags = parseCommaSeparatedTags(value);
    setEditedTags(parsedTags.length > 0 ? parsedTags : fallbackTags);
    setIsEditing(false);
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-body-bold font-body-bold text-default-font">
        {label}
      </label>
      <p className="text-caption font-caption text-subtext-color">{description}</p>
      <TagsManager
        tags={editedTags}
        onTagsChange={(tags) => {
          setEditedTags(tags);
          setIsEditing(true);
        }}
        label=""
        placeholder="Enter tags and press Enter"
      />
      {isEditing && (
        <div className="flex gap-2">
          <Button variant="brand-primary" size="small" onClick={handleSave}>
            <Save className="text-[16px]" />
            Save
          </Button>
          <Button variant="neutral-secondary" size="small" onClick={handleCancel}>
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
}

function BooleanSettingField({
  label,
  description,
  value,
  onSave,
  disabled = false,
}: BooleanSettingFieldProps) {
  const handleChange = (checked: boolean) => {
    onSave(checked);
  };

  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex flex-col gap-1">
        <label className={`text-body-bold font-body-bold ${disabled ? 'text-subtext-color' : 'text-default-font'}`}>
          {label}
        </label>
        <p className="text-caption font-caption text-subtext-color">{description}</p>
      </div>
      <Switch
        checked={value}
        onCheckedChange={handleChange}
        disabled={disabled}
      />
    </div>
  );
}

export default AdminSettings;
