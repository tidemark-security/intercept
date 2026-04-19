import React from "react";
import { Button } from "@/components/buttons/Button";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { IconButton } from "@/components/buttons/IconButton";
import { IconWithBackground } from "@/components/misc/IconWithBackground";
import { TextField } from "@/components/forms/TextField";
import type { ApiKeyCreateResponse } from "@/types/generated/models/ApiKeyCreateResponse";
import {
  AlertCircle,
  Bluetooth,
  Check,
  Copy,
  Eye,
  EyeOff,
  Key,
  Nfc,
  Smartphone,
  Trash2,
  Usb,
} from "lucide-react";

interface ApiKeySecurityCardProps {
  name: string;
  prefix: string;
  createdAt?: string | null;
  expiresAt?: string | null;
  lastUsedAt?: string | null;
  revokedAt?: string | null;
  isExpired: boolean;
  formatDate: (dateValue?: string | null) => string;
  onRevoke?: () => void;
  revokeLoading?: boolean;
}

export function ApiKeySecurityCard({
  name,
  prefix,
  createdAt,
  expiresAt,
  lastUsedAt,
  revokedAt,
  isExpired,
  formatDate,
  onRevoke,
  revokeLoading = false,
}: ApiKeySecurityCardProps) {
  return (
    <div className="flex w-full flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background">
      <div className="flex w-full items-center gap-4 px-4 py-4">
        <IconWithBackground variant="neutral" size="large" icon={<Key />} />

        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <div className="flex items-center gap-2">
            <span className="text-body-bold font-body-bold text-default-font">
              {name}
            </span>
            <code className="text-caption font-mono text-subtext-color">
              {prefix}...
            </code>
            {revokedAt && (
              <span className="text-caption font-caption text-error-500">
                Revoked
              </span>
            )}
            {!revokedAt && isExpired && (
              <span className="text-caption font-caption text-warning-500">
                Expired
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <span className="text-caption font-caption text-subtext-color">
              Created: {formatDate(createdAt)}
            </span>
            <span className="text-caption font-caption text-subtext-color">
              Expires: {formatDate(expiresAt)}
            </span>
            {lastUsedAt && (
              <span className="text-caption font-caption text-subtext-color">
                Last used: {formatDate(lastUsedAt)}
              </span>
            )}
          </div>
        </div>

        {!revokedAt && onRevoke && (
          <IconButton
            icon={<Trash2 />}
            variant="destructive-secondary"
            onClick={onRevoke}
            loading={revokeLoading}
          />
        )}
      </div>
    </div>
  );
}

interface PasskeySecurityCardProps {
  name: string;
  createdAt?: string | null;
  lastUsedAt?: string | null;
  transports?: string[];
  isBackedUp?: boolean;
  revokedAt?: string | null;
  formatDate: (dateValue?: string | null) => string;
  onRemove?: () => void;
  removeLoading?: boolean;
  rightActions?: React.ReactNode;
}

export function formatPasskeyTransports(transports?: string[]): string {
  if (!transports || transports.length === 0) {
    return "Unknown";
  }

  return transports
    .map((transport) => {
      switch (transport) {
        case "ble":
          return "Bluetooth";
        case "hybrid":
          return "Hybrid";
        case "internal":
          return "Internal";
        case "nfc":
          return "NFC";
        case "usb":
          return "USB";
        default:
          return transport;
      }
    })
    .join(", ");
}

export function getPasskeyIconFromTransports(transports?: string[]): React.ReactNode {
  const availableTransports = transports || [];
  if (
    availableTransports.includes("internal") ||
    availableTransports.includes("hybrid")
  ) {
    return <Smartphone />;
  }
  if (availableTransports.includes("usb")) {
    return <Usb />;
  }
  if (availableTransports.includes("nfc")) {
    return <Nfc />;
  }
  if (availableTransports.includes("ble")) {
    return <Bluetooth />;
  }
  return <Key />;
}

export function PasskeySecurityCard({
  name,
  createdAt,
  lastUsedAt,
  transports,
  isBackedUp,
  revokedAt,
  formatDate,
  onRemove,
  removeLoading = false,
  rightActions,
}: PasskeySecurityCardProps) {
  return (
    <div className="flex w-full flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background">
      <div className="flex w-full items-center gap-4 px-4 py-4">
        <IconWithBackground
          variant="neutral"
          size="large"
          icon={getPasskeyIconFromTransports(transports)}
        />

        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <div className="flex items-center gap-2">
            <span className="text-body-bold font-body-bold text-default-font">
              {name}
            </span>
            {revokedAt && (
              <span className="text-caption font-caption text-error-500">
                Revoked
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <span className="text-caption font-caption text-subtext-color">
              Registered: {formatDate(createdAt)}
            </span>
            <span className="text-caption font-caption text-subtext-color">
              Last used: {formatDate(lastUsedAt)}
            </span>
            <span className="text-caption font-caption text-subtext-color">
              Transports: {formatPasskeyTransports(transports)}
            </span>
            {typeof isBackedUp === "boolean" && (
              <span className="text-caption font-caption text-subtext-color">
                Backup: {isBackedUp ? "Backed up" : "Not backed up"}
              </span>
            )}
          </div>
        </div>

        {rightActions ??
          (!revokedAt &&
            onRemove && (
              <IconButton
                icon={<Trash2 />}
                variant="destructive-secondary"
                onClick={onRemove}
                loading={removeLoading}
              />
            ))}
      </div>
    </div>
  );
}

interface ApiKeyCreatedContentProps {
  createdApiKey: ApiKeyCreateResponse;
  showValue: boolean;
  copied: boolean;
  onToggleValue: () => void;
  onCopy: () => void;
  onDone: () => void;
  formatDate: (dateValue?: string | null) => string;
  successIcon?: React.ReactNode;
}

export function ApiKeyCreatedContent({
  createdApiKey,
  showValue,
  copied,
  onToggleValue,
  onCopy,
  onDone,
  formatDate,
  successIcon,
}: ApiKeyCreatedContentProps) {
  return (
    <>
      <div className="flex w-full items-center gap-2">
        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <span className="text-heading-2 font-heading-2 text-default-font flex items-center gap-2">
            {successIcon ?? <Check className="text-success-500" />}
            API Key Created
          </span>
          <span className="text-body font-body text-subtext-color">
            Copy this key now. It will not be shown again.
          </span>
        </div>
      </div>

      <div className="flex w-full flex-col gap-3 rounded-md border border-solid border-warning-300 bg-warning-50 px-4 py-4">
        <div className="flex items-center gap-2">
          <AlertCircle className="text-warning-500" />
          <span className="text-body-bold font-body-bold text-warning-700">
            Store this key securely
          </span>
        </div>
        <div className="flex w-full items-center gap-2">
          <code className="flex-1 rounded-md bg-default-background px-3 py-2 font-mono text-body break-all">
            {showValue ? createdApiKey.key : "•".repeat(48)}
          </code>
          <IconButton
            icon={showValue ? <EyeOff /> : <Eye />}
            onClick={onToggleValue}
            variant="inverse"
          />
          <IconButton
            icon={copied ? <Check className="text-success-500" /> : <Copy />}
            onClick={onCopy}
            variant="inverse"
          />
        </div>
      </div>

      <div className="flex w-full flex-col gap-2 text-body text-subtext-color">
        <div className="flex justify-between">
          <span>Name:</span>
          <span className="text-default-font">{createdApiKey.name}</span>
        </div>
        <div className="flex justify-between">
          <span>Prefix:</span>
          <code className="text-default-font">{createdApiKey.prefix}</code>
        </div>
        <div className="flex justify-between">
          <span>Expires:</span>
          <span className="text-default-font">
            {formatDate(createdApiKey.expires_at)}
          </span>
        </div>
      </div>

      <div className="flex w-full items-center justify-end">
        <Button onClick={onDone}>Done</Button>
      </div>
    </>
  );
}

interface CreateApiKeyModalContentProps {
  keyName: string;
  expiresAt: string;
  onKeyNameChange: (value: string) => void;
  onExpiresAtChange: (value: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
  loading?: boolean;
  keyNamePlaceholder?: string;
}

export function CreateApiKeyModalContent({
  keyName,
  expiresAt,
  onKeyNameChange,
  onExpiresAtChange,
  onCancel,
  onSubmit,
  loading = false,
  keyNamePlaceholder = "Automation Key",
}: CreateApiKeyModalContentProps) {
  return (
    <>
      <div className="flex w-full items-center gap-2">
        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <span className="text-heading-2 font-heading-2 text-default-font">
            Create API Key
          </span>
          <span className="text-body font-body text-subtext-color">
            The key will only be shown once after creation.
          </span>
        </div>
        <Key className="text-[24px] text-default-font" />
      </div>

      <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-6 px-4 py-4">
          <TextField
            className="h-auto w-full flex-none"
            label="Key Name"
            helpText="A descriptive name for this API key"
          >
            <TextField.Input
              placeholder={keyNamePlaceholder}
              value={keyName}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                onKeyNameChange(event.target.value)
              }
            />
          </TextField>

          <DateTimeManager
            className="h-auto w-full flex-none"
            label="Expiration Date"
            helpText="When this API key should expire"
            value={expiresAt}
            onChange={onExpiresAtChange}
            showNowButton={false}
          />
        </div>
      </div>

      <div className="flex w-full items-center justify-end gap-2">
        <Button variant="neutral-secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button onClick={onSubmit} loading={loading}>
          Create Key
        </Button>
      </div>
    </>
  );
}
