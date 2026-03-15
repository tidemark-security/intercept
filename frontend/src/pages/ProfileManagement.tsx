"use client";

import React from "react";
import { ApiError } from "@/types/generated/core/ApiError";
import { ApiKeysService } from "@/types/generated/services/ApiKeysService";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import { Alert } from "@/components/feedback/Alert";
import {
  ApiKeyCreatedContent,
  ApiKeySecurityCard,
  CreateApiKeyModalContent,
  PasskeySecurityCard,
} from "@/components/auth";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { IconButton } from "@/components/buttons/IconButton";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { ModalShell } from "@/components/overlays";
import { Select } from "@/components/forms/Select";
import { Slider } from "@/components/forms/Slider";
import { TextField } from "@/components/forms/TextField";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { useTheme } from "@/contexts/ThemeContext";
import { useTimezonePreference } from "@/contexts/TimezoneContext";
import { useToast } from "@/contexts/ToastContext";
import { useVisualFilterPreference } from "@/contexts/VisualFilterContext";
import type { ApiKeyCreateResponse } from "@/types/generated/models/ApiKeyCreateResponse";
import type { ApiKeyRead } from "@/types/generated/models/ApiKeyRead";
import type { PasskeyRead } from "@/types/generated/models/PasskeyRead";
import {
  formatForDatetimeLocal,
  normalizeDatetimeLocalValue,
  parseISO8601,
} from "@/utils/dateFilters";
import { formatAbsoluteTime } from "@/utils/dateFormatters";
import type { ThemePreference } from "@/utils/themePreference";
import type { TimezonePreference } from "@/utils/timezonePreference";
import {
  getVisualFilterLimits,
  type VisualFilterPreference,
} from "@/utils/visualFilterPreference";
import { browserSupportsPasskeys, createPasskeyCredential } from "@/utils/webauthn";

import {
  AlertCircle,
  Check,
  Edit2,
  Fingerprint,
  Key,
  Lock,
  Monitor,
  MoreHorizontal,
  Plus,
  SlidersHorizontal,
  Shield,
  Trash2,
} from "lucide-react";

const visualFilterLimits = getVisualFilterLimits();

const visualFilterPreviewSwatches = [
  { label: "Brand", variable: "--color-brand-primary-blush", textClass: "text-black" },
  { label: "Text", variable: "--color-default-font" },
  { label: "Subtext", variable: "--color-subtext-color" },
  { label: "Border", variable: "--color-neutral-border" },
  { label: "Accent 1", variable: "--color-accent-1-primary-blush", textClass: "text-black" },
  { label: "Accent 2", variable: "--color-accent-2-primary-blush", textClass: "text-white" },
  { label: "Accent 3", variable: "--color-accent-3-primary-blush", textClass: "text-white" },
];

const formatDate = (dateValue?: string | null): string => {
  if (!dateValue) return "Never";
  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) return "Unknown";
  return parsed.toLocaleDateString();
};

const formatApiKeyDate = (dateValue?: string | null): string => {
  if (!dateValue) return "Never";
  return formatAbsoluteTime(dateValue, "MMM d, yyyy");
};

const isApiKeyExpired = (expiresAt: string | null | undefined): boolean => {
  if (!expiresAt) return false;
  const parsed = parseISO8601(expiresAt);
  if (!parsed) return false;
  return parsed.getTime() < Date.now();
};

type PasskeyModalMode = "register" | "rename";

function ProfileManagement() {
  const { themePreference, setThemePreference } = useTheme();
  const { timezonePreference, setTimezonePreference } = useTimezonePreference();
  const {
    visualFilterPreference,
    setVisualFilterPreference,
    resetVisualFilterPreference,
  } = useVisualFilterPreference();
  const { showToast } = useToast();
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [apiKeys, setApiKeys] = React.useState<ApiKeyRead[]>([]);
  const [isLoadingApiKeys, setIsLoadingApiKeys] = React.useState(false);
  const [isCreatingApiKey, setIsCreatingApiKey] = React.useState(false);
  const [showCreateApiKeyModal, setShowCreateApiKeyModal] = React.useState(false);
  const [apiKeyNameInput, setApiKeyNameInput] = React.useState("");
  const [apiKeyExpiresAtInput, setApiKeyExpiresAtInput] = React.useState("");
  const [createdApiKey, setCreatedApiKey] = React.useState<ApiKeyCreateResponse | null>(null);
  const [showCreatedApiKeyValue, setShowCreatedApiKeyValue] = React.useState(true);
  const [createdApiKeyCopied, setCreatedApiKeyCopied] = React.useState(false);
  const [passkeys, setPasskeys] = React.useState<PasskeyRead[]>([]);
  const [isLoadingPasskeys, setIsLoadingPasskeys] = React.useState(false);
  const [isRegisteringPasskey, setIsRegisteringPasskey] = React.useState(false);
  const [isRenamingPasskey, setIsRenamingPasskey] = React.useState(false);
  const [isChangingPassword, setIsChangingPassword] = React.useState(false);
  const [showPasskeyModal, setShowPasskeyModal] = React.useState(false);
  const [passkeyModalMode, setPasskeyModalMode] = React.useState<PasskeyModalMode>("register");
  const [passkeyNameInput, setPasskeyNameInput] = React.useState("");
  const [selectedPasskey, setSelectedPasskey] = React.useState<PasskeyRead | null>(null);

  const loadPasskeys = React.useCallback(async () => {
    setIsLoadingPasskeys(true);
    try {
      const items = await AuthenticationService.listOwnPasskeysApiV1AuthPasskeysGet();
      setPasskeys(items);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setPasskeys([]);
        return;
      }
      showToast("Error", "Failed to load passkeys", "error");
    } finally {
      setIsLoadingPasskeys(false);
    }
  }, [showToast]);

  const loadApiKeys = React.useCallback(async () => {
    setIsLoadingApiKeys(true);
    try {
      const items = await ApiKeysService.listApiKeysApiV1ApiKeysGet({
        includeRevoked: true,
      });
      setApiKeys(items);
    } catch (error) {
      showToast("Error", "Failed to load API keys", "error");
    } finally {
      setIsLoadingApiKeys(false);
    }
  }, [showToast]);

  React.useEffect(() => {
    loadPasskeys();
  }, [loadPasskeys]);

  React.useEffect(() => {
    loadApiKeys();
  }, [loadApiKeys]);

  const handleChangePassword = async () => {
    if (!currentPassword.trim() || !newPassword.trim() || !confirmPassword.trim()) {
      showToast("Validation Error", "All password fields are required", "error");
      return;
    }
    if (newPassword !== confirmPassword) {
      showToast("Validation Error", "New passwords do not match", "error");
      return;
    }

    setIsChangingPassword(true);
    try {
      await AuthenticationService.changePasswordApiV1AuthPasswordChangePost({
        requestBody: {
          currentPassword,
          newPassword,
        },
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      if (error instanceof ApiError) {
        showToast("Error", error.body?.message || "Password update failed", "error");
      } else {
        showToast("Error", "Password update failed", "error");
      }
    } finally {
      setIsChangingPassword(false);
    }
  };

  const closePasskeyModal = React.useCallback(() => {
    setShowPasskeyModal(false);
    setPasskeyNameInput("");
    setSelectedPasskey(null);
  }, []);

  const openCreateApiKeyModal = () => {
    const defaultExpiry = new Date();
    defaultExpiry.setDate(defaultExpiry.getDate() + 30);
    setApiKeyNameInput("");
    setApiKeyExpiresAtInput(
      normalizeDatetimeLocalValue(formatForDatetimeLocal(defaultExpiry), "display"),
    );
    setShowCreateApiKeyModal(true);
  };

  const closeCreateApiKeyModal = () => {
    setShowCreateApiKeyModal(false);
    setApiKeyNameInput("");
    setApiKeyExpiresAtInput("");
  };

  const closeCreatedApiKeyModal = () => {
    setCreatedApiKey(null);
    setShowCreatedApiKeyValue(true);
    setCreatedApiKeyCopied(false);
  };

  const handleCreateApiKey = async () => {
    if (!apiKeyNameInput.trim() || !apiKeyExpiresAtInput) {
      showToast("Validation Error", "Name and expiration date are required", "error");
      return;
    }

    const expiresAtDate = parseISO8601(apiKeyExpiresAtInput);
    if (!expiresAtDate) {
      showToast("Validation Error", "Expiration date is invalid", "error");
      return;
    }

    setIsCreatingApiKey(true);
    try {
      const response = await ApiKeysService.createApiKeyApiV1ApiKeysPost({
        requestBody: {
          name: apiKeyNameInput.trim(),
          expires_at: expiresAtDate.toISOString(),
        },
      });

      setCreatedApiKey(response);
      setShowCreatedApiKeyValue(true);
      closeCreateApiKeyModal();
      await loadApiKeys();
    } catch (error) {
      if (error instanceof ApiError) {
        showToast("Error", error.body?.message || "Failed to create API key", "error");
      } else {
        showToast("Error", "Failed to create API key", "error");
      }
    } finally {
      setIsCreatingApiKey(false);
    }
  };

  const handleRevokeApiKey = async (apiKeyId: string) => {
    try {
      await ApiKeysService.revokeApiKeyApiV1ApiKeysApiKeyIdDelete({ apiKeyId });
      await loadApiKeys();
    } catch (error) {
      if (error instanceof ApiError) {
        showToast("Error", error.body?.message || "Failed to revoke API key", "error");
      } else {
        showToast("Error", "Failed to revoke API key", "error");
      }
    }
  };

  const handleCopyApiKey = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key);
      setCreatedApiKeyCopied(true);
      window.setTimeout(() => setCreatedApiKeyCopied(false), 2000);
    } catch {
      showToast("Error", "Failed to copy API key", "error");
    }
  };

  const openRegisterPasskeyModal = () => {
    if (!browserSupportsPasskeys()) {
      showToast("Unsupported", "This browser does not support passkeys", "error");
      return;
    }

    setPasskeyModalMode("register");
    setSelectedPasskey(null);
    setPasskeyNameInput("My Passkey");
    setShowPasskeyModal(true);
  };

  const openRenamePasskeyModal = (passkey: PasskeyRead) => {
    setPasskeyModalMode("rename");
    setSelectedPasskey(passkey);
    setPasskeyNameInput(passkey.name);
    setShowPasskeyModal(true);
  };

  const handleSubmitPasskeyModal = React.useCallback(async () => {
    const trimmedName = passkeyNameInput.trim();
    if (!trimmedName) {
      showToast("Validation Error", "Passkey name is required", "error");
      return;
    }

    if (passkeyModalMode === "rename") {
      if (!selectedPasskey) {
        return;
      }
      if (trimmedName === selectedPasskey.name) {
        closePasskeyModal();
        return;
      }

      setIsRenamingPasskey(true);
      try {
        await AuthenticationService.renameOwnPasskeyApiV1AuthPasskeysPasskeyIdPatch({
          passkeyId: selectedPasskey.id,
          requestBody: { name: trimmedName },
        });
        await loadPasskeys();
        closePasskeyModal();
      } catch (error) {
        if (error instanceof ApiError) {
          showToast("Error", error.body?.message || "Failed to rename passkey", "error");
        } else {
          showToast("Error", "Failed to rename passkey", "error");
        }
      } finally {
        setIsRenamingPasskey(false);
      }
      return;
    }

    setIsRegisteringPasskey(true);
    try {
      const begin = await AuthenticationService.beginPasskeyRegistrationApiV1AuthPasskeysRegisterOptionsPost({
        requestBody: {},
      });
      const credential = await createPasskeyCredential(begin.options);
      await AuthenticationService.finishPasskeyRegistrationApiV1AuthPasskeysRegisterVerifyPost({
        requestBody: {
          challenge: begin.challenge,
          name: trimmedName,
          credential,
        },
      });
      await loadPasskeys();
      closePasskeyModal();
    } catch (error) {
      if (error instanceof ApiError) {
        showToast("Error", error.body?.message || "Passkey registration failed", "error");
      } else if (error instanceof Error) {
        showToast("Error", error.message, "error");
      } else {
        showToast("Error", "Passkey registration failed", "error");
      }
    } finally {
      setIsRegisteringPasskey(false);
    }
  }, [
    closePasskeyModal,
    loadPasskeys,
    passkeyModalMode,
    passkeyNameInput,
    selectedPasskey,
    showToast,
  ]);

  React.useEffect(() => {
    if (!showPasskeyModal) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!isRegisteringPasskey && !isRenamingPasskey) {
          closePasskeyModal();
        }
        return;
      }

      if (event.key === "Enter") {
        const activeElement = document.activeElement;
        const isInputElement =
          activeElement instanceof HTMLInputElement ||
          activeElement instanceof HTMLTextAreaElement;

        if (!isInputElement || isRegisteringPasskey || isRenamingPasskey) {
          return;
        }

        const trimmedName = passkeyNameInput.trim();
        if (
          !trimmedName ||
          (passkeyModalMode === "rename" &&
            trimmedName === selectedPasskey?.name)
        ) {
          return;
        }

        event.preventDefault();
        void handleSubmitPasskeyModal();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    closePasskeyModal,
    handleSubmitPasskeyModal,
    isRegisteringPasskey,
    isRenamingPasskey,
    passkeyModalMode,
    passkeyNameInput,
    selectedPasskey,
    showPasskeyModal,
  ]);

  const handleRevokePasskey = async (passkey: PasskeyRead) => {
    try {
      await AuthenticationService.revokeOwnPasskeyApiV1AuthPasskeysPasskeyIdDelete({
        passkeyId: passkey.id,
      });
      await loadPasskeys();
    } catch (error) {
      if (error instanceof ApiError) {
        showToast("Error", error.body?.message || "Failed to remove passkey", "error");
      } else {
        showToast("Error", "Failed to remove passkey", "error");
      }
    }
  };

  const updateVisualFilter = React.useCallback(
    (patch: Partial<VisualFilterPreference>) => {
      setVisualFilterPreference((previous) => ({ ...previous, ...patch }));
    },
    [setVisualFilterPreference],
  );

  return (
    <DefaultPageLayout withContainer>
      <div className="flex h-full w-full flex-col items-start gap-6 overflow-auto px-6 py-12 mobile:px-4 mobile:py-6">
        <div className="mx-auto flex w-full max-w-7xl flex-col items-start gap-6">
          <div className="flex w-full flex-col items-start gap-2">
            <span className="text-heading-1 font-heading-1 text-default-font">
              Profile Management
            </span>
            <span className="text-body font-body text-subtext-color">
              Manage your password, API keys, and passkeys to keep your account secure.
            </span>
          </div>

          <div className="flex w-full flex-col items-start gap-8">
            <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-6 py-6">
              <div className="flex w-full items-center gap-2">
                <IconWithBackground
                  variant="neutral"
                  size="medium"
                  icon={<Monitor />}
                />
                <span className="grow shrink-0 basis-0 text-heading-2 font-heading-2 text-default-font">
                  Appearance
                </span>
              </div>

              <span className="text-body font-body text-subtext-color">
                Choose how the app theme is applied on this device.
              </span>

              <Select
                className="h-auto w-full max-w-[320px]"
                variant="filled"
                label="Theme"
                value={themePreference}
                onValueChange={(value) => setThemePreference(value as ThemePreference)}
              >
                <Select.Item value="system">System default</Select.Item>
                <Select.Item value="dark">Dark</Select.Item>
                <Select.Item value="light">Light</Select.Item>
              </Select>

              <Select
                className="h-auto w-full max-w-[320px]"
                variant="filled"
                label="Timezone"
                value={timezonePreference}
                onValueChange={(value) => setTimezonePreference(value as TimezonePreference)}
              >
                <Select.Item value="local">Local</Select.Item>
                <Select.Item value="utc">UTC</Select.Item>
              </Select>

              <div className="flex w-full max-w-3xl flex-col items-start gap-4 rounded-md border border-solid border-neutral-border bg-default-background px-4 py-4">
                <div className="flex w-full items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="text-heading-3 text-subtext-color" />
                    <span className="text-caption-bold font-caption-bold text-default-font">
                      Visual Filter
                    </span>
                  </div>
                  <Button
                    size="small"
                    variant="neutral-secondary"
                    onClick={resetVisualFilterPreference}
                  >
                    Reset
                  </Button>
                </div>

                <span className="text-caption font-caption text-subtext-color">
                  Tune hue shift, brightness, contrast, grayscale, and saturation for the full app on this device.
                </span>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Theme Colors Preview</span>
                  <div className="flex flex-wrap items-center gap-2">
                    {visualFilterPreviewSwatches.map((swatch) => (
                      <div
                        key={swatch.label}
                        className="flex h-8 min-w-[64px] items-center justify-center rounded border border-solid border-neutral-border px-2"
                        style={{ backgroundColor: `rgb(var(${swatch.variable}))` }}
                        title={swatch.label}
                      >
                        <span
                          className={`text-[11px] font-medium leading-none ${swatch.textClass ?? "text-neutral-0"}`}
                        >
                          {swatch.label}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Hue Shift</span>
                  <Slider
                    value={[visualFilterPreference.hue]}
                    min={visualFilterLimits.hue.min}
                    max={visualFilterLimits.hue.max}
                    step={1}
                    onValueChange={(value) => updateVisualFilter({ hue: value[0] })}
                  />
                  <div className="flex w-full items-center justify-between">
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.hue.min}deg
                    </span>
                    <span className="text-caption font-caption text-default-font">
                      {visualFilterPreference.hue}deg
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.hue.max}deg
                    </span>
                  </div>
                </div>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Brightness</span>
                  <Slider
                    value={[visualFilterPreference.brightness]}
                    min={visualFilterLimits.brightness.min}
                    max={visualFilterLimits.brightness.max}
                    step={1}
                    onValueChange={(value) => updateVisualFilter({ brightness: value[0] })}
                  />
                  <div className="flex w-full items-center justify-between">
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.brightness.min}%
                    </span>
                    <span className="text-caption font-caption text-default-font">
                      {visualFilterPreference.brightness}%
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.brightness.max}%
                    </span>
                  </div>
                </div>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Contrast</span>
                  <Slider
                    value={[visualFilterPreference.contrast]}
                    min={visualFilterLimits.contrast.min}
                    max={visualFilterLimits.contrast.max}
                    step={1}
                    onValueChange={(value) => updateVisualFilter({ contrast: value[0] })}
                  />
                  <div className="flex w-full items-center justify-between">
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.contrast.min}%
                    </span>
                    <span className="text-caption font-caption text-default-font">
                      {visualFilterPreference.contrast}%
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.contrast.max}%
                    </span>
                  </div>
                </div>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Grayscale</span>
                  <Slider
                    value={[visualFilterPreference.grayscale]}
                    min={visualFilterLimits.grayscale.min}
                    max={visualFilterLimits.grayscale.max}
                    step={1}
                    onValueChange={(value) => updateVisualFilter({ grayscale: value[0] })}
                  />
                  <div className="flex w-full items-center justify-between">
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.grayscale.min}%
                    </span>
                    <span className="text-caption font-caption text-default-font">
                      {visualFilterPreference.grayscale}%
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.grayscale.max}%
                    </span>
                  </div>
                </div>

                <div className="flex w-full flex-col items-start gap-2">
                  <span className="text-caption-bold font-caption-bold text-default-font">Saturation</span>
                  <Slider
                    value={[visualFilterPreference.saturation]}
                    min={visualFilterLimits.saturation.min}
                    max={visualFilterLimits.saturation.max}
                    step={1}
                    onValueChange={(value) => updateVisualFilter({ saturation: value[0] })}
                  />
                  <div className="flex w-full items-center justify-between">
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.saturation.min}%
                    </span>
                    <span className="text-caption font-caption text-default-font">
                      {visualFilterPreference.saturation}%
                    </span>
                    <span className="text-caption font-caption text-subtext-color">
                      {visualFilterLimits.saturation.max}%
                    </span>
                  </div>
                </div>

              </div>
            </div>

            <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-6 py-6">
              <div className="flex w-full items-center gap-2">
                <IconWithBackground
                  variant="neutral"
                  size="medium"
                  icon={<Lock />}
                />
                <span className="grow shrink-0 basis-0 text-heading-2 font-heading-2 text-default-font">
                  Password
                </span>
              </div>

              <div className="flex w-full flex-col items-start gap-4">
                <TextField
                  className="h-auto w-full flex-none"
                  variant="filled"
                  label="Current Password"
                >
                  <TextField.Input
                    type="password"
                    placeholder="Enter current password"
                    value={currentPassword}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                      setCurrentPassword(event.target.value)
                    }
                  />
                </TextField>

                <TextField
                  className="h-auto w-full flex-none"
                  variant="filled"
                  label="New Password"
                >
                  <TextField.Input
                    type="password"
                    placeholder="Enter new password"
                    value={newPassword}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                      setNewPassword(event.target.value)
                    }
                  />
                </TextField>

                <TextField
                  className="h-auto w-full flex-none"
                  variant="filled"
                  label="Confirm New Password"
                >
                  <TextField.Input
                    type="password"
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                      setConfirmPassword(event.target.value)
                    }
                  />
                </TextField>
              </div>

              <div className="flex w-full flex-col items-end gap-6">
                <Button icon={<Key />} onClick={handleChangePassword} disabled={isChangingPassword}>
                  {isChangingPassword ? "Changing..." : "Change Password"}
                </Button>
              </div>
            </div>

            <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-6 py-6">
              <div className="flex w-full flex-wrap items-center gap-2">
                <IconWithBackground
                  variant="neutral"
                  size="medium"
                  icon={<Key />}
                />
                <span className="grow shrink-0 basis-0 text-heading-2 font-heading-2 text-default-font">
                  API Keys
                </span>
                <Button icon={<Plus />} onClick={openCreateApiKeyModal} disabled={isCreatingApiKey}>
                  Create New API Key
                </Button>
              </div>

              <span className="text-body font-body text-subtext-color">
                API keys are for programmatic access to your account.
              </span>

              <div className="flex w-full flex-col items-start gap-4">
                {isLoadingApiKeys ? (
                  <span className="text-body font-body text-subtext-color">Loading API keys...</span>
                ) : apiKeys.length === 0 ? (
                  <span className="text-body font-body text-subtext-color">
                    No API keys registered yet.
                  </span>
                ) : apiKeys.map((apiKey) => (
                  <ApiKeySecurityCard
                    key={apiKey.id}
                    name={apiKey.name}
                    prefix={apiKey.prefix}
                    createdAt={apiKey.created_at}
                    expiresAt={apiKey.expires_at}
                    lastUsedAt={apiKey.last_used_at}
                    revokedAt={apiKey.revoked_at}
                    isExpired={isApiKeyExpired(apiKey.expires_at)}
                    formatDate={formatApiKeyDate}
                    onRevoke={() => handleRevokeApiKey(apiKey.id)}
                  />
                ))}
              </div>
            </div>

            <div className="flex w-full flex-col items-start gap-6 rounded-md border border-solid border-neutral-border bg-neutral-50 px-6 py-6">
              <div className="flex w-full flex-wrap items-center gap-2">
                <IconWithBackground
                  variant="neutral"
                  size="medium"
                  icon={<Fingerprint />}
                />
                <span className="grow shrink-0 basis-0 text-heading-2 font-heading-2 text-default-font">
                  Passkeys
                </span>
                <Button icon={<Plus />} onClick={openRegisterPasskeyModal} disabled={isRegisteringPasskey}>
                  {isRegisteringPasskey ? "Registering..." : "Register New Passkey"}
                </Button>
              </div>

              <span className="text-body font-body text-subtext-color">
                Passkeys are a more secure alternative to passwords. Use your
                device biometrics or security key to sign in.
              </span>

              <div className="flex w-full flex-col items-start gap-4">
                {isLoadingPasskeys ? (
                  <span className="text-body font-body text-subtext-color">Loading passkeys...</span>
                ) : passkeys.length === 0 ? (
                  <span className="text-body font-body text-subtext-color">
                    No passkeys registered yet.
                  </span>
                ) : passkeys.map((passkey) => (
                  <PasskeySecurityCard
                    key={passkey.id}
                    name={passkey.name}
                    createdAt={passkey.createdAt}
                    lastUsedAt={passkey.lastUsedAt}
                    transports={passkey.transports}
                    isBackedUp={passkey.isBackedUp}
                    formatDate={formatDate}
                    rightActions={
                      <DropdownMenu.Root>
                        <DropdownMenu.Trigger asChild>
                          <IconButton icon={<MoreHorizontal />} />
                        </DropdownMenu.Trigger>
                        <DropdownMenu.Content side="bottom" align="end" sideOffset={4}>
                          <DropdownMenu.DropdownItem
                            icon={<Edit2 />}
                            hint=""
                            label="Rename"
                            onSelect={() => openRenamePasskeyModal(passkey)}
                          />
                          <DropdownMenu.DropdownItem
                            icon={<Trash2 />}
                            hint=""
                            label="Remove"
                            onSelect={() => handleRevokePasskey(passkey)}
                          />
                        </DropdownMenu.Content>
                      </DropdownMenu.Root>
                    }
                  />
                ))}
              </div>

              <Alert
                variant="neutral"
                icon={<Shield />}
                title="Enhance your security"
                description="We recommend registering at least two passkeys on different devices to ensure you always have a backup authentication method."
              />
            </div>
          </div>
        </div>
      </div>

      {showPasskeyModal && (
        <ModalShell>
          <div className="flex w-full items-center gap-2">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
              <span className="text-heading-2 font-heading-2 text-default-font">
                {passkeyModalMode === "register" ? "Register Passkey" : "Rename Passkey"}
              </span>
              <span className="text-body font-body text-subtext-color">
                {passkeyModalMode === "register"
                  ? "Choose a descriptive name for your new passkey"
                  : "Update the display name for this passkey"}
              </span>
            </div>
            <Fingerprint className="text-[24px] text-default-font" />
          </div>

          <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-6 px-4 py-4">
              {passkeyModalMode === "register" && !isLoadingPasskeys && passkeys.length === 0 && (
                <div className="flex w-full flex-col gap-3 rounded-md border border-solid border-warning-300 bg-warning-50 px-4 py-4">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="text-warning-500" />
                    <span className="text-body-bold font-body-bold text-warning-700">
                      Important account change
                    </span>
                  </div>
                  <span className="text-body font-body text-default-font">
                    Registering your first passkey will disable password-based login for this account.
                  </span>
                </div>
              )}

              <TextField
                className="h-auto w-full flex-none"
                label="Passkey Name"
                helpText="A friendly name to identify this passkey"
              >
                <TextField.Input
                  placeholder="My Passkey"
                  value={passkeyNameInput}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                    setPasskeyNameInput(event.target.value)
                  }
                />
              </TextField>
            </div>
          </div>

          <div className="flex w-full items-center justify-end gap-2">
            <Button
              variant="neutral-secondary"
              onClick={closePasskeyModal}
              disabled={isRegisteringPasskey || isRenamingPasskey}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmitPasskeyModal}
              loading={passkeyModalMode === "register" ? isRegisteringPasskey : isRenamingPasskey}
              disabled={
                !passkeyNameInput.trim() ||
                (passkeyModalMode === "rename" &&
                  passkeyNameInput.trim() === selectedPasskey?.name)
              }
            >
              {passkeyModalMode === "register" ? "Register Passkey" : "Save Name"}
            </Button>
          </div>
        </ModalShell>
      )}

      {showCreateApiKeyModal && (
        <ModalShell>
          <CreateApiKeyModalContent
            keyName={apiKeyNameInput}
            expiresAt={apiKeyExpiresAtInput}
            onKeyNameChange={setApiKeyNameInput}
            onExpiresAtChange={setApiKeyExpiresAtInput}
            onCancel={closeCreateApiKeyModal}
            onSubmit={handleCreateApiKey}
            loading={isCreatingApiKey}
            keyNamePlaceholder="Automation Key"
          />
        </ModalShell>
      )}

      {createdApiKey && (
        <ModalShell>
          <ApiKeyCreatedContent
            createdApiKey={createdApiKey}
            showValue={showCreatedApiKeyValue}
            copied={createdApiKeyCopied}
            onToggleValue={() => setShowCreatedApiKeyValue((prev) => !prev)}
            onCopy={() => handleCopyApiKey(createdApiKey.key)}
            onDone={closeCreatedApiKeyModal}
            formatDate={formatApiKeyDate}
            successIcon={<Check className="text-success-500" />}
          />
        </ModalShell>
      )}
    </DefaultPageLayout>
  );
}

export default ProfileManagement;
