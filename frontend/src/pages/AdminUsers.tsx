import React, { useMemo, useState, useCallback } from "react";
import {
  ApiKeyCreatedContent,
  ApiKeySecurityCard,
  CreateApiKeyModalContent,
  PasskeySecurityCard,
} from "@/components/auth";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/data-display/Badge";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { IconButton } from "@/components/buttons/IconButton";
import { ModalShell } from "@/components/overlays";
import { Table } from "@/components/data-display/Table";
import { TextField } from "@/components/forms/TextField";
import { Toast } from "@/components/feedback/Toast";
import { ToggleGroup } from "@/components/buttons/ToggleGroup";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { AdminPageLayout } from "../components/layout/AdminPageLayout";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import {
  formatForDatetimeLocal,
  normalizeDatetimeLocalValue,
  parseISO8601,
} from "@/utils/dateFilters";
import { formatAbsoluteTime, formatTimelineTimestamp } from "@/utils/dateFormatters";
import { AdminService } from "../types/generated/services/AdminService";
import { ApiKeysService } from "../types/generated/services/ApiKeysService";
import type {
  AccountType,
  UserRole,
  UserStatus,
  ApiKeyRead,
  ApiKeyCreateResponse,
  AdminCreateNHIResponse,
  AdminPasskeyRead,
} from "../types/generated";
import { ApiError } from "../types/generated";
import { useSession } from "../contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";

import {
  AlertCircle,
  Ban,
  Bot,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Crown,
  Fingerprint,
  Key,
  ListChecks,
  Lock,
  Microscope,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  User,
  UserCheck,
  UserPlus,
  UserX,
} from "lucide-react";
interface User {
  id: string;
  username: string;
  email: string;
  description: string;
  accountType: AccountType;
  role: UserRole;
  status: UserStatus;
  mustChangePassword: boolean;
  lastLoginAt: string | null;
  createdAt: string;
}

interface CreateUserFormData {
  accountType: "HUMAN" | "NHI";
  username: string;
  email: string;
  role: UserRole;
  // NHI-specific fields
  description: string;
  initialApiKeyName: string;
  initialApiKeyExpiresAt: string;
}

interface CreateApiKeyFormData {
  name: string;
  expiresAt: string;
  userId: string;
}

interface UnifiedCreatedKeyData {
  key: ApiKeyCreateResponse;
  onDone: () => void;
}

const USER_QUERY_KEY = ["admin-users"] as const;
const ACTION_SUCCESS_TIMEOUT_MS = 3000;
const CREATE_SUCCESS_TIMEOUT_MS = 2000;

const INITIAL_CREATE_FORM_DATA: CreateUserFormData = {
  accountType: "HUMAN",
  username: "",
  email: "",
  role: "ANALYST",
  description: "",
  initialApiKeyName: "",
  initialApiKeyExpiresAt: "",
};

const EMPTY_API_KEY_FORM_DATA: CreateApiKeyFormData = {
  name: "",
  expiresAt: "",
  userId: "",
};

const ALLOWED_ROLES: UserRole[] = ["ANALYST", "ADMIN", "AUDITOR"];
const ALLOWED_STATUSES: UserStatus[] = ["ACTIVE", "DISABLED", "LOCKED"];
const STATUS_BADGE_VARIANTS: Record<
  UserStatus,
  "neutral" | "error" | "warning"
> = {
  ACTIVE: "neutral",
  DISABLED: "error",
  LOCKED: "warning",
};
const ROLE_BADGE_VARIANTS: Record<UserRole, "neutral" | "error"> = {
  ADMIN: "error",
  ANALYST: "neutral",
  AUDITOR: "neutral",
};

function normalizeUserRole(value: unknown): UserRole {
  return typeof value === "string" && ALLOWED_ROLES.includes(value as UserRole)
    ? (value as UserRole)
    : "ANALYST";
}

function normalizeUserStatus(value: unknown): UserStatus {
  return typeof value === "string" &&
    ALLOWED_STATUSES.includes(value as UserStatus)
    ? (value as UserStatus)
    : "ACTIVE";
}

function normalizeAccountType(value: unknown): AccountType {
  return value === "NHI" ? "NHI" : "HUMAN";
}

function mapApiUser(raw: Record<string, unknown>): User {
  return {
    id: typeof raw.id === "string" ? raw.id : "",
    username: typeof raw.username === "string" ? raw.username : "",
    email: typeof raw.email === "string" ? raw.email : "",
    description: typeof raw.description === "string" ? raw.description : "",
    accountType: normalizeAccountType(raw.accountType ?? raw.account_type),
    role: normalizeUserRole(raw.role),
    status: normalizeUserStatus(raw.status),
    mustChangePassword: Boolean(raw.mustChangePassword),
    lastLoginAt: typeof raw.lastLoginAt === "string" ? raw.lastLoginAt : null,
    createdAt: typeof raw.createdAt === "string" ? raw.createdAt : "",
  };
}

function AdminUsers() {
  const { user: currentUser } = useSession();
  const { resolvedTheme } = useTheme();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRole | "ALL">("ALL");
  const [statusFilter, setStatusFilter] = useState<UserStatus | "ALL">("ALL");

  // Create user modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createFormData, setCreateFormData] = useState<CreateUserFormData>(
    INITIAL_CREATE_FORM_DATA,
  );
  const [createLoading, setCreateLoading] = useState(false);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [createdNhiResponse, setCreatedNhiResponse] =
    useState<AdminCreateNHIResponse | null>(null);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editFormData, setEditFormData] = useState<CreateUserFormData>(
    INITIAL_CREATE_FORM_DATA,
  );
  const [editLoading, setEditLoading] = useState(false);

  // Action states
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // API Key states
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [userApiKeys, setUserApiKeys] = useState<Record<string, ApiKeyRead[]>>(
    {},
  );
  const [apiKeysLoading, setApiKeysLoading] = useState<string | null>(null);
  const [userPasskeys, setUserPasskeys] = useState<
    Record<string, AdminPasskeyRead[]>
  >({});
  const [passkeysLoading, setPasskeysLoading] = useState<string | null>(null);
  const [showCreateApiKeyModal, setShowCreateApiKeyModal] = useState(false);
  const [createApiKeyFormData, setCreateApiKeyFormData] =
    useState<CreateApiKeyFormData>(EMPTY_API_KEY_FORM_DATA);
  const [createApiKeyLoading, setCreateApiKeyLoading] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] =
    useState<ApiKeyCreateResponse | null>(null);
  const [showKeyValue, setShowKeyValue] = useState(false);
  const [keyCopied, setKeyCopied] = useState(false);

  // Check if current user is admin
  const isAdmin = currentUser?.role === "ADMIN";

  // Helper function to extract error message from API responses
  const extractErrorMessage = useCallback(
    (err: any, fallback: string): string => {
      if (err instanceof ApiError) {
        // FastAPI HTTPException with detail containing ValidationErrorResponse
        if (err.body && typeof err.body === "object" && "detail" in err.body) {
          const detail = err.body.detail;
          if (
            typeof detail === "object" &&
            detail !== null &&
            "message" in detail
          ) {
            return detail.message;
          }
        }
        // Direct message in body
        if (err.body && typeof err.body === "object" && "message" in err.body) {
          return err.body.message;
        }
      }
      // Fall back to the error message
      if (err instanceof Error) {
        return err.message;
      }
      return fallback;
    },
    [],
  );

  const {
    data: usersResponse = [],
    isLoading: loading,
    error: usersQueryError,
  } = useQuery({
    queryKey: USER_QUERY_KEY,
    queryFn: () => AdminService.listUsersApiV1AdminAuthUsersGet(),
    enabled: isAdmin,
  });

  const users = useMemo(() => {
    return usersResponse
      .filter(
        (record): record is Record<string, unknown> =>
          Boolean(record) && typeof record === "object",
      )
      .map(mapApiUser);
  }, [usersResponse]);

  const activeError =
    error ??
    (usersQueryError
      ? extractErrorMessage(usersQueryError, "Failed to load users")
      : null);

  const refreshUsers = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: USER_QUERY_KEY });
  }, [queryClient]);

  const showActionSuccess = useCallback((message: string) => {
    setActionSuccess(message);
    setTimeout(() => setActionSuccess(null), ACTION_SUCCESS_TIMEOUT_MS);
  }, []);

  const resetCreateForm = () => {
    setCreateFormData(INITIAL_CREATE_FORM_DATA);
  };

  const updateCreateFormField = <K extends keyof CreateUserFormData>(
    field: K,
    value: CreateUserFormData[K],
  ) => {
    setCreateFormData((prev) => ({ ...prev, [field]: value }));
  };

  const updateCreateApiKeyField = <K extends keyof CreateApiKeyFormData>(
    field: K,
    value: CreateApiKeyFormData[K],
  ) => {
    setCreateApiKeyFormData((prev) => ({ ...prev, [field]: value }));
  };

  const updateEditFormField = <K extends keyof CreateUserFormData>(
    field: K,
    value: CreateUserFormData[K],
  ) => {
    setEditFormData((prev) => ({ ...prev, [field]: value }));
  };

  const closeCreateUserModal = () => {
    setShowCreateModal(false);
    resetCreateForm();
    setCreateSuccess(null);
    setError(null);
  };

  const closeEditUserModal = () => {
    setEditingUser(null);
    setEditFormData(INITIAL_CREATE_FORM_DATA);
    setError(null);
  };

  const closeCreateApiKeyModal = () => {
    setShowCreateApiKeyModal(false);
    setCreateApiKeyFormData(EMPTY_API_KEY_FORM_DATA);
  };

  const handleCreateUser = async () => {
    if (!createFormData.username) {
      setError("Username is required");
      return;
    }

    if (createFormData.accountType === "HUMAN") {
      if (!createFormData.email) {
        setError("Email is required for human accounts");
        return;
      }

      try {
        setCreateLoading(true);
        setError(null);
        await AdminService.createUserApiV1AdminAuthUsersPost({
          requestBody: {
            username: createFormData.username,
            email: createFormData.email,
            role: createFormData.role,
            description: createFormData.description || undefined,
          },
        });

        setCreateSuccess(
          `User created successfully. Temporary credentials sent to ${createFormData.email}`,
        );
        resetCreateForm();

        // Reload users list
        await refreshUsers();

        // Close modal after 2 seconds
        setTimeout(() => {
          setShowCreateModal(false);
          setCreateSuccess(null);
        }, CREATE_SUCCESS_TIMEOUT_MS);
      } catch (err) {
        setError(extractErrorMessage(err, "Failed to create user"));
      } finally {
        setCreateLoading(false);
      }
    } else {
      // NHI account creation
      if (!createFormData.initialApiKeyName) {
        setError("API key name is required for NHI accounts");
        return;
      }
      if (!createFormData.initialApiKeyExpiresAt) {
        setError("API key expiration date is required for NHI accounts");
        return;
      }

      const initialApiKeyExpiresAtDate = parseISO8601(
        createFormData.initialApiKeyExpiresAt,
      );
      if (!initialApiKeyExpiresAtDate) {
        setError("API key expiration date is invalid");
        return;
      }

      try {
        setCreateLoading(true);
        setError(null);
        const response =
          await AdminService.createNhiAccountApiV1AdminAuthUsersNhiPost({
            requestBody: {
              username: createFormData.username,
              role: createFormData.role,
              description: createFormData.description || undefined,
              initial_api_key_name: createFormData.initialApiKeyName,
              initial_api_key_expires_at:
                initialApiKeyExpiresAtDate.toISOString(),
            },
          });

        // Store the response to show the API key
        setCreatedNhiResponse(response);
        setCreateSuccess(
          `NHI account "${response.username}" created successfully`,
        );

        // Reload users list
        await refreshUsers();
      } catch (err) {
        setError(extractErrorMessage(err, "Failed to create NHI account"));
      } finally {
        setCreateLoading(false);
      }
    }
  };

  const handleOpenEditUserModal = (user: User) => {
    setEditingUser(user);
    setEditFormData({
      accountType: user.accountType,
      username: user.username,
      email: user.email,
      role: user.role,
      description: user.description,
      initialApiKeyName: "",
      initialApiKeyExpiresAt: "",
    });
    setError(null);
  };

  const handleEditUser = async () => {
    if (!editingUser) {
      return;
    }

    if (!editFormData.username.trim()) {
      setError("Username is required");
      return;
    }

    if (editingUser.accountType === "HUMAN" && !editFormData.email.trim()) {
      setError("Email is required for human accounts");
      return;
    }

    try {
      setEditLoading(true);
      setError(null);
      await AdminService.updateUserApiV1AdminAuthUsersUserIdPatch({
        userId: editingUser.id,
        requestBody: {
          username: editFormData.username,
          email:
            editingUser.accountType === "HUMAN"
              ? editFormData.email
              : undefined,
          role: editFormData.role,
          description: editFormData.description,
        },
      });

      await refreshUsers();
      closeEditUserModal();
      showActionSuccess("User updated successfully");
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to update user"));
    } finally {
      setEditLoading(false);
    }
  };

  const handleUpdateStatus = async (userId: string, newStatus: UserStatus) => {
    try {
      setActionLoading(userId);
      setError(null);
      await AdminService.updateUserStatusApiV1AdminAuthUsersUserIdStatusPatch({
        userId,
        requestBody: { status: newStatus },
      });

      showActionSuccess(
        `User ${newStatus === "ACTIVE" ? "enabled" : "disabled"} successfully`,
      );
      await refreshUsers();
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to update user status"));
    } finally {
      setActionLoading(null);
    }
  };

  const handleResetPassword = async (userId: string) => {
    try {
      setActionLoading(userId);
      setError(null);
      await AdminService.issuePasswordResetApiV1AdminAuthPasswordResetsPost({
        requestBody: { userId },
      });

      showActionSuccess("Password reset issued successfully");
      await refreshUsers();
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to issue password reset"));
    } finally {
      setActionLoading(null);
    }
  };

  // API Key Management Functions
  const loadUserApiKeys = async (userId: string) => {
    try {
      setApiKeysLoading(userId);
      const keys = await ApiKeysService.listApiKeysApiV1ApiKeysGet({
        userId,
        includeRevoked: true,
      });
      setUserApiKeys((prev) => ({ ...prev, [userId]: keys }));
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to load API keys"));
    } finally {
      setApiKeysLoading(null);
    }
  };

  const handleToggleExpandUser = async (user: User) => {
    if (expandedUserId === user.id) {
      setExpandedUserId(null);
    } else {
      setExpandedUserId(user.id);
      if (!userApiKeys[user.id]) {
        await loadUserApiKeys(user.id);
      }
      if (user.accountType !== "NHI" && !userPasskeys[user.id]) {
        await loadUserPasskeys(user.id);
      }
    }
  };

  const loadUserPasskeys = async (userId: string) => {
    try {
      setPasskeysLoading(userId);
      const passkeys =
        await AdminService.listUserPasskeysApiV1AdminAuthUsersUserIdPasskeysGet(
          {
            userId,
          },
        );
      setUserPasskeys((prev) => ({ ...prev, [userId]: passkeys }));
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to load passkeys"));
    } finally {
      setPasskeysLoading(null);
    }
  };

  const handleOpenCreateApiKeyModal = (userId: string) => {
    // Default expiration to 30 days from now
    const defaultExpiry = new Date();
    defaultExpiry.setDate(defaultExpiry.getDate() + 30);
    setCreateApiKeyFormData({
      name: "",
      expiresAt: normalizeDatetimeLocalValue(
        formatForDatetimeLocal(defaultExpiry),
        "display",
      ),
      userId,
    });
    setShowCreateApiKeyModal(true);
  };

  const handleCreateApiKey = async () => {
    if (!createApiKeyFormData.name || !createApiKeyFormData.expiresAt) {
      setError("Name and expiration date are required");
      return;
    }

    const expiresAtDate = parseISO8601(createApiKeyFormData.expiresAt);
    if (!expiresAtDate) {
      setError("Expiration date is invalid");
      return;
    }

    try {
      setCreateApiKeyLoading(true);
      setError(null);
      const response = await ApiKeysService.createApiKeyApiV1ApiKeysPost({
        requestBody: {
          name: createApiKeyFormData.name,
          expires_at: expiresAtDate.toISOString(),
          user_id: createApiKeyFormData.userId,
        },
      });

      setNewlyCreatedKey(response);
      setShowKeyValue(true);

      // Reload the user's API keys
      await loadUserApiKeys(createApiKeyFormData.userId);
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to create API key"));
    } finally {
      setCreateApiKeyLoading(false);
    }
  };

  const handleRevokeApiKey = async (apiKeyId: string, userId: string) => {
    try {
      setActionLoading(apiKeyId);
      setError(null);
      await ApiKeysService.revokeApiKeyApiV1ApiKeysApiKeyIdDelete({ apiKeyId });
      showActionSuccess("API key revoked successfully");
      await loadUserApiKeys(userId);
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to revoke API key"));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevokePasskey = async (passkeyId: string, userId: string) => {
    try {
      setActionLoading(passkeyId);
      setError(null);
      await AdminService.revokeUserPasskeyApiV1AdminAuthUsersUserIdPasskeysPasskeyIdDelete(
        {
          userId,
          passkeyId,
        },
      );
      showActionSuccess("Passkey revoked successfully");
      await loadUserPasskeys(userId);
    } catch (err) {
      setError(extractErrorMessage(err, "Failed to revoke passkey"));
    } finally {
      setActionLoading(null);
    }
  };

  const handleCopyKey = async (key: string) => {
    try {
      await navigator.clipboard.writeText(key);
      setKeyCopied(true);
      setTimeout(() => setKeyCopied(false), 2000);
    } catch (err) {
      setError("Failed to copy to clipboard");
    }
  };

  const closeCreatedKeyModal = () => {
    setCreatedNhiResponse(null);
    setNewlyCreatedKey(null);
    setShowCreateModal(false);
    setShowKeyValue(false);
    setKeyCopied(false);
    setShowCreateApiKeyModal(false);
    setCreateSuccess(null);
    resetCreateForm();
    setCreateApiKeyFormData(EMPTY_API_KEY_FORM_DATA);
  };

  const renderCreatedKeyModal = ({ key, onDone }: UnifiedCreatedKeyData) => (
    <ModalShell>
      <ApiKeyCreatedContent
        createdApiKey={key}
        showValue={showKeyValue}
        copied={keyCopied}
        onToggleValue={() => setShowKeyValue((previousValue) => !previousValue)}
        onCopy={() => handleCopyKey(key.key)}
        onDone={onDone}
        formatDate={formatApiKeyDate}
        successIcon={<CheckCircle className="text-success-500" />}
      />
    </ModalShell>
  );

  const createdKeyModalData: UnifiedCreatedKeyData | null = createdNhiResponse
    ? { key: createdNhiResponse.apiKey, onDone: closeCreatedKeyModal }
    : newlyCreatedKey
      ? { key: newlyCreatedKey, onDone: closeCreatedKeyModal }
      : null;

  const formatApiKeyDate = (dateString?: string | null) => {
    if (!dateString) return "Never";
    return formatAbsoluteTime(dateString, "MMM d, yyyy");
  };

  const isApiKeyExpired = (expiresAt: string) => {
    const expiresAtDate = parseISO8601(expiresAt);
    if (!expiresAtDate) {
      return false;
    }
    return expiresAtDate.getTime() < Date.now();
  };

  const sortApiKeysForDisplay = (apiKeys: ApiKeyRead[]) => {
    const toExpiryTimestamp = (expiresAt: string | null | undefined) => {
      if (!expiresAt) {
        return Number.POSITIVE_INFINITY;
      }
      const parsedDate = parseISO8601(expiresAt);
      return parsedDate ? parsedDate.getTime() : Number.POSITIVE_INFINITY;
    };

    return [...apiKeys].sort((leftKey, rightKey) => {
      const leftRevoked = Boolean(leftKey.revoked_at);
      const rightRevoked = Boolean(rightKey.revoked_at);

      if (leftRevoked !== rightRevoked) {
        return leftRevoked ? 1 : -1;
      }

      if (!leftRevoked) {
        return (
          toExpiryTimestamp(leftKey.expires_at) -
          toExpiryTimestamp(rightKey.expires_at)
        );
      }

      return 0;
    });
  };

  const sortPasskeysForDisplay = (passkeys: AdminPasskeyRead[]) => {
    const toCreatedTimestamp = (createdAt: string | null | undefined) => {
      if (!createdAt) {
        return Number.NEGATIVE_INFINITY;
      }
      const parsedDate = parseISO8601(createdAt);
      return parsedDate ? parsedDate.getTime() : Number.NEGATIVE_INFINITY;
    };

    return [...passkeys].sort((leftPasskey, rightPasskey) => {
      const leftRevoked = Boolean(leftPasskey.revokedAt);
      const rightRevoked = Boolean(rightPasskey.revokedAt);

      if (leftRevoked !== rightRevoked) {
        return leftRevoked ? 1 : -1;
      }

      return (
        toCreatedTimestamp(rightPasskey.createdAt) -
        toCreatedTimestamp(leftPasskey.createdAt)
      );
    });
  };

  const renderApiKeyCard = (apiKey: ApiKeyRead, userId: string) => (
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
      onRevoke={() => handleRevokeApiKey(apiKey.id, userId)}
      revokeLoading={actionLoading === apiKey.id}
    />
  );

  const renderPasskeyCard = (passkey: AdminPasskeyRead, userId: string) => (
    <PasskeySecurityCard
      key={passkey.id}
      name={passkey.name}
      createdAt={passkey.createdAt}
      lastUsedAt={passkey.lastUsedAt}
      transports={passkey.transports}
      revokedAt={passkey.revokedAt}
      formatDate={formatApiKeyDate}
      onRemove={() => handleRevokePasskey(passkey.id, userId)}
      removeLoading={actionLoading === passkey.id}
    />
  );

  const renderExpandedSecurityRow = (user: User) => {
    const canCreateApiKeyForUser = user.accountType === "NHI";
    const apiKeys = userApiKeys[user.id] ?? [];
    const sortedApiKeys = sortApiKeysForDisplay(apiKeys);
    const passkeys = userPasskeys[user.id] ?? [];
    const sortedPasskeys = sortPasskeysForDisplay(passkeys);

    return (
      <tr
        className={`border-t border-neutral-border ${resolvedTheme === "dark" ? "bg-neutral-100" : "bg-neutral-200"}`}
      >
        <td colSpan={8} className="px-6 py-4">
          <div className="flex w-full flex-col gap-4">
            <div className="flex w-full items-center justify-between">
              <span className="text-body-bold font-body-bold text-default-font flex items-center gap-2">
                <Key className="text-neutral-400" />
                API Keys
              </span>
              {canCreateApiKeyForUser ? (
                <Button
                  size="small"
                  icon={<Plus />}
                  onClick={() => handleOpenCreateApiKeyModal(user.id)}
                >
                  New Key
                </Button>
              ) : (
                <span className="text-caption font-caption text-subtext-color">
                  Human users create keys from Profile Management
                </span>
              )}
            </div>

            {apiKeysLoading === user.id ? (
              <span className="text-body font-body text-subtext-color">
                Loading API keys...
              </span>
            ) : apiKeys.length === 0 ? (
              <div className="flex items-center gap-2 text-body font-body text-subtext-color py-2">
                <Key className="text-neutral-500" />
                No API keys configured for this user
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {sortedApiKeys.map((apiKey) => renderApiKeyCard(apiKey, user.id))}
              </div>
            )}

            {user.accountType !== "NHI" && (
              <>
                <div className="h-px w-full bg-neutral-border" />

                <div className="flex w-full items-center justify-between">
                  <span className="text-body-bold font-body-bold text-default-font flex items-center gap-2">
                    <Fingerprint className="text-neutral-400" />
                    Passkeys
                  </span>
                </div>

                {passkeysLoading === user.id ? (
                  <span className="text-body font-body text-subtext-color">
                    Loading passkeys...
                  </span>
                ) : passkeys.length === 0 ? (
                  <div className="flex items-center gap-2 text-body font-body text-subtext-color py-2">
                    <Fingerprint className="text-neutral-500" />
                    No passkeys configured for this user
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {sortedPasskeys.map((passkey) =>
                      renderPasskeyCard(passkey, user.id),
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </td>
      </tr>
    );
  };

  const renderUserActions = (user: User) => {
    const isCurrentUser = user.id === currentUser?.id;

    return (
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <IconButton
            icon={<MoreHorizontal />}
            loading={actionLoading === user.id}
          />
        </DropdownMenu.Trigger>
        <DropdownMenu.Content side="bottom" align="end" sideOffset={8}>
          <DropdownMenu.DropdownItem
            icon={<Pencil />}
            label="Edit User"
            onClick={() => handleOpenEditUserModal(user)}
          />
          <DropdownMenu.DropdownDivider />
          {user.accountType !== "NHI" && (
            <DropdownMenu.DropdownItem
              icon={<Key />}
              label="Reset Password"
              onClick={() => handleResetPassword(user.id)}
              disabled={isCurrentUser}
            />
          )}
          {user.accountType === "NHI" && (
            <DropdownMenu.DropdownItem
              icon={<Plus />}
              label="Create API Key"
              onClick={() => handleOpenCreateApiKeyModal(user.id)}
            />
          )}
          <DropdownMenu.DropdownDivider />
          {user.status === "ACTIVE" ? (
            <DropdownMenu.DropdownItem
              icon={<UserX />}
              label="Disable Account"
              onClick={() => handleUpdateStatus(user.id, "DISABLED")}
              disabled={isCurrentUser}
            />
          ) : (
            <DropdownMenu.DropdownItem
              icon={<UserCheck />}
              label="Enable Account"
              onClick={() => handleUpdateStatus(user.id, "ACTIVE")}
            />
          )}
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    );
  };

  const filteredUsers = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();

    return users
      .filter((user) => {
        const matchesSearch =
          normalizedSearch.length === 0 ||
          user.username.toLowerCase().includes(normalizedSearch) ||
          user.email.toLowerCase().includes(normalizedSearch);
        const matchesRole = roleFilter === "ALL" || user.role === roleFilter;
        const matchesStatus =
          statusFilter === "ALL" || user.status === statusFilter;
        return matchesSearch && matchesRole && matchesStatus;
      })
      .sort((a, b) =>
        a.username.toLowerCase().localeCompare(b.username.toLowerCase()),
      );
  }, [users, searchQuery, roleFilter, statusFilter]);

  const getStatusBadgeVariant = (status: UserStatus) =>
    STATUS_BADGE_VARIANTS[status] ?? "neutral";

  const getRoleBadgeVariant = (role: UserRole) =>
    ROLE_BADGE_VARIANTS[role] ?? "neutral";

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Never";
    return formatTimelineTimestamp(dateString, {
      useRelative: true,
      relativeDaysThreshold: 7,
      absoluteFormat: "MMM d, yyyy",
    });
  };

  if (!isAdmin) {
    return (
      <DefaultPageLayout >
        <div className="container max-w-none flex h-full w-full flex-col items-center justify-center gap-4 bg-default-background">
          <AlertCircle className="text-[48px] text-error text-error-500" />
          <span className="text-heading-2 font-heading-2 text-default-font">
            Access Denied
          </span>
          <span className="text-body font-body text-subtext-color">
            Admin privileges required to access user management
          </span>
        </div>
      </DefaultPageLayout>
    );
  }

  return (
    <>
      <AdminPageLayout
        title="User Management"
        subtitle="Manage users, roles, and account status"

        actionButton={
          <Button icon={<UserPlus />} onClick={() => setShowCreateModal(true)}>
            Add User
          </Button>
        }
      >
        {/* Filters */}
        <div
          className={`flex w-full flex-col items-start gap-2 p-2 ${resolvedTheme === "dark" ? "bg-neutral-100" : "bg-neutral-300"}`}
        >
          <div className="flex w-full flex-wrap items-center gap-4">
            <TextField
              className="h-auto grow shrink-0 basis-0 "
              variant="outline"
              label=""
              helpText=""
              icon={<Search />}
            >
              <TextField.Input
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </TextField>
          </div>
          <div className="flex w-full items-start gap-2 rounded-md">
            <ToggleGroup
              className="h-auto flex-1"
              value={roleFilter === "ALL" ? "" : roleFilter}
              onValueChange={(value) =>
                setRoleFilter(value ? (value as UserRole) : "ALL")
              }
            >
              <ToggleGroup.Item
                className="flex-1"
                icon={<Crown />}
                value="ADMIN"
              >
                Admin
              </ToggleGroup.Item>
              <ToggleGroup.Item
                className="flex-1"
                icon={<Microscope />}
                value="ANALYST"
              >
                Analyst
              </ToggleGroup.Item>

              <ToggleGroup.Item
                className="flex-1"
                icon={<ListChecks />}
                value="AUDITOR"
              >
                Auditor
              </ToggleGroup.Item>
            </ToggleGroup>
            <ToggleGroup
              className="h-auto flex-1"
              value={statusFilter === "ALL" ? "" : statusFilter}
              onValueChange={(value) =>
                setStatusFilter(value ? (value as UserStatus) : "ALL")
              }
            >
              <ToggleGroup.Item
                className="flex-1"
                icon={<CheckCircle />}
                value="ACTIVE"
              >
                Active
              </ToggleGroup.Item>
              <ToggleGroup.Item
                className="flex-1"
                icon={<Ban />}
                value="DISABLED"
              >
                Disabled
              </ToggleGroup.Item>
              <ToggleGroup.Item
                className="flex-1"
                icon={<Lock />}
                value="LOCKED"
              >
                Locked
              </ToggleGroup.Item>
            </ToggleGroup>
          </div>
        </div>

        {/* Users Table */}
        {loading ? (
          <div className="flex w-full items-center justify-center py-12">
            <span className="text-body font-body text-subtext-color">
              Loading users...
            </span>
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="flex w-full items-center justify-center py-12">
            <span className="text-body font-body text-subtext-color">
              No users found
            </span>
          </div>
        ) : (
          <div className="flex w-full flex-col items-start overflow-auto">
            <Table
              header={
                <Table.HeaderRow>
                  <Table.HeaderCell></Table.HeaderCell>
                  <Table.HeaderCell>Username</Table.HeaderCell>
                  <Table.HeaderCell>Type</Table.HeaderCell>
                  <Table.HeaderCell>Email</Table.HeaderCell>
                  <Table.HeaderCell>Role</Table.HeaderCell>
                  <Table.HeaderCell>Status</Table.HeaderCell>
                  <Table.HeaderCell>Last Login</Table.HeaderCell>
                  <Table.HeaderCell />
                </Table.HeaderRow>
              }
            >
              {filteredUsers.map((user) => (
                <React.Fragment key={user.id}>
                  <Table.Row>
                    <Table.Cell>
                      <IconButton
                        icon={
                          expandedUserId === user.id ? (
                            <ChevronDown />
                          ) : (
                            <ChevronRight />
                          )
                        }
                        size="small"
                        onClick={() => handleToggleExpandUser(user)}
                      />
                    </Table.Cell>
                    <Table.Cell>
                      <div className="flex flex-col gap-1">
                        <span className="whitespace-nowrap text-body-bold font-body-bold text-default-font">
                          {user.username}
                        </span>
                        {user.mustChangePassword && (
                          <span className="text-caption font-caption text-error-500">
                            Must change password
                          </span>
                        )}
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      <div className="flex items-center">
                        {user.accountType === "NHI" ? (
                          <Bot className="text-neutral-500" />
                        ) : (
                          <User className="text-neutral-500" />
                        )}
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      <span className="whitespace-nowrap text-body font-body text-neutral-500">
                        {user.email}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge variant={getRoleBadgeVariant(user.role)}>
                        {user.role}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge variant={getStatusBadgeVariant(user.status)}>
                        {user.status}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>
                      <span className="whitespace-nowrap text-body font-body text-neutral-500">
                        {formatDate(user.lastLoginAt)}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      <div className="flex grow shrink-0 basis-0 items-center justify-end">
                        {renderUserActions(user)}
                      </div>
                    </Table.Cell>
                  </Table.Row>
                  {/* Expanded API Keys Row */}
                  {expandedUserId === user.id &&
                    renderExpandedSecurityRow(user)}
                </React.Fragment>
              ))}
            </Table>
          </div>
        )}
      </AdminPageLayout>

      {/* Create User Modal */}
      {showCreateModal && !createdNhiResponse && (
        <ModalShell>
          {/* Modal Header */}
          <div className="flex w-full items-center gap-2">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
              <span className="text-heading-2 font-heading-2 text-default-font">
                Create New User
              </span>
              <span className="text-body font-body text-subtext-color">
                {createFormData.accountType === "HUMAN"
                  ? "User will receive temporary credentials via email"
                  : "Create a service account for programmatic API access"}
              </span>
            </div>
            <UserPlus className="text-[24px] text-default-font" />
          </div>

          {/* Form */}
          <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-6 px-4 py-4">
              {/* Account Type Selection */}
              <div className="flex w-full flex-col items-start gap-2">
                <span className="text-body-bold font-body-bold text-default-font">
                  Account Type
                </span>
                <div className="flex w-full gap-2">
                  <Button
                    variant={
                      createFormData.accountType === "HUMAN"
                        ? "brand-primary"
                        : "neutral-secondary"
                    }
                    icon={<User />}
                    onClick={() =>
                      updateCreateFormField("accountType", "HUMAN")
                    }
                  >
                    Human
                  </Button>
                  <Button
                    variant={
                      createFormData.accountType === "NHI"
                        ? "brand-primary"
                        : "neutral-secondary"
                    }
                    icon={<Bot />}
                    onClick={() => updateCreateFormField("accountType", "NHI")}
                  >
                    Service (NHI)
                  </Button>
                </div>
              </div>

              <TextField
                className="h-auto w-full flex-none"
                label="Username"
                helpText="Lowercase, 3-1024 characters, letters, numbers, '.', '_', or '-'"
              >
                <TextField.Input
                  placeholder={
                    createFormData.accountType === "HUMAN"
                      ? "analyst.user"
                      : "svc.integration"
                  }
                  value={createFormData.username}
                  onChange={(e) =>
                    updateCreateFormField("username", e.target.value)
                  }
                />
              </TextField>

              {createFormData.accountType === "HUMAN" ? (
                <>
                  <TextField
                    className="h-auto w-full flex-none"
                    label="Email"
                    helpText="Used for temporary credential delivery"
                  >
                    <TextField.Input
                      type="email"
                      placeholder="analyst@example.com"
                      value={createFormData.email}
                      onChange={(e) =>
                        updateCreateFormField("email", e.target.value)
                      }
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Job Title / Description"
                    helpText="User's job title or role description (optional)"
                  >
                    <TextField.Input
                      placeholder="Senior Security Analyst"
                      value={createFormData.description}
                      onChange={(e) =>
                        updateCreateFormField("description", e.target.value)
                      }
                    />
                  </TextField>
                </>
              ) : (
                <>
                  <TextField
                    className="h-auto w-full flex-none"
                    label="Description"
                    helpText="Purpose or description of this service account (optional)"
                  >
                    <TextField.Input
                      placeholder="Integration with SIEM platform"
                      value={createFormData.description}
                      onChange={(e) =>
                        updateCreateFormField("description", e.target.value)
                      }
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Initial API Key Name"
                    helpText="A descriptive name for the initial API key"
                  >
                    <TextField.Input
                      placeholder="production-key"
                      value={createFormData.initialApiKeyName}
                      onChange={(e) =>
                        updateCreateFormField(
                          "initialApiKeyName",
                          e.target.value,
                        )
                      }
                    />
                  </TextField>

                  <DateTimeManager
                    className="h-auto w-full flex-none"
                    label="API Key Expiration"
                    helpText="When the initial API key should expire"
                    value={createFormData.initialApiKeyExpiresAt}
                    onChange={(value) =>
                      updateCreateFormField("initialApiKeyExpiresAt", value)
                    }
                    showNowButton={false}
                  />
                </>
              )}

              {/* Role Selection */}
              <div className="flex w-full flex-col items-start gap-2">
                <span className="text-body-bold font-body-bold text-default-font">
                  Role
                </span>
                <div className="flex w-full gap-2">
                  {ALLOWED_ROLES.map((role) => (
                    <Button
                      key={role}
                      variant={
                        createFormData.role === role
                          ? "brand-primary"
                          : "neutral-secondary"
                      }
                      onClick={() => updateCreateFormField("role", role)}
                    >
                      {role}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex w-full items-center justify-end gap-2">
            <Button
              variant="neutral-secondary"
              onClick={closeCreateUserModal}
              disabled={createLoading}
            >
              Cancel
            </Button>
            <Button onClick={handleCreateUser} loading={createLoading}>
              {createFormData.accountType === "HUMAN"
                ? "Create User"
                : "Create Service Account"}
            </Button>
          </div>
        </ModalShell>
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <ModalShell>
          <div className="flex w-full items-center gap-2">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
              <span className="text-heading-2 font-heading-2 text-default-font">
                Edit User
              </span>
              <span className="text-body font-body text-subtext-color">
                {editingUser.accountType === "HUMAN"
                  ? "Update the user account details and role"
                  : "Update the service account details and role"}
              </span>
            </div>
            {editingUser.accountType === "NHI" ? (
              <Bot className="text-[24px] text-default-font" />
            ) : (
              <User className="text-[24px] text-default-font" />
            )}
          </div>

          <div className="flex w-full items-start rounded-md border border-solid border-neutral-border bg-default-background">
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-6 px-4 py-4">
              <TextField
                className="h-auto w-full flex-none"
                label="Username"
                helpText="Lowercase, 3-1024 characters, letters, numbers, '.', '_', or '-'"
              >
                <TextField.Input
                  placeholder={
                    editingUser.accountType === "HUMAN"
                      ? "analyst.user"
                      : "svc.integration"
                  }
                  value={editFormData.username}
                  onChange={(e) =>
                    updateEditFormField("username", e.target.value)
                  }
                />
              </TextField>

              {editingUser.accountType === "HUMAN" ? (
                <>
                  <TextField
                    className="h-auto w-full flex-none"
                    label="Email"
                    helpText="Used for temporary credential delivery"
                  >
                    <TextField.Input
                      type="email"
                      placeholder="analyst@example.com"
                      value={editFormData.email}
                      onChange={(e) =>
                        updateEditFormField("email", e.target.value)
                      }
                    />
                  </TextField>

                  <TextField
                    className="h-auto w-full flex-none"
                    label="Job Title / Description"
                    helpText="User's job title or role description (optional)"
                  >
                    <TextField.Input
                      placeholder="Senior Security Analyst"
                      value={editFormData.description}
                      onChange={(e) =>
                        updateEditFormField("description", e.target.value)
                      }
                    />
                  </TextField>
                </>
              ) : (
                <TextField
                  className="h-auto w-full flex-none"
                  label="Description"
                  helpText="Purpose or description of this service account (optional)"
                >
                  <TextField.Input
                    placeholder="Integration with SIEM platform"
                    value={editFormData.description}
                    onChange={(e) =>
                      updateEditFormField("description", e.target.value)
                    }
                  />
                </TextField>
              )}

              <div className="flex w-full flex-col items-start gap-2">
                <span className="text-body-bold font-body-bold text-default-font">
                  Role
                </span>
                <div className="flex w-full gap-2">
                  {ALLOWED_ROLES.map((role) => (
                    <Button
                      key={role}
                      variant={
                        editFormData.role === role
                          ? "brand-primary"
                          : "neutral-secondary"
                      }
                      onClick={() => updateEditFormField("role", role)}
                    >
                      {role}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="flex w-full items-center justify-end gap-2">
            <Button
              variant="neutral-secondary"
              onClick={closeEditUserModal}
              disabled={editLoading}
            >
              Cancel
            </Button>
            <Button onClick={handleEditUser} loading={editLoading}>
              Save Changes
            </Button>
          </div>
        </ModalShell>
      )}

      {/* Create API Key Modal */}
      {showCreateApiKeyModal && !newlyCreatedKey && (
        <ModalShell>
          <CreateApiKeyModalContent
            keyName={createApiKeyFormData.name}
            expiresAt={createApiKeyFormData.expiresAt}
            onKeyNameChange={(value) => updateCreateApiKeyField("name", value)}
            onExpiresAtChange={(value) => updateCreateApiKeyField("expiresAt", value)}
            onCancel={closeCreateApiKeyModal}
            onSubmit={handleCreateApiKey}
            loading={createApiKeyLoading}
            keyNamePlaceholder="CI/CD Pipeline"
          />
        </ModalShell>
      )}

      {/* Unified API Key Created Modal - shown for both NHI and direct key creation */}
      {createdKeyModalData && renderCreatedKeyModal(createdKeyModalData)}

      {/* Toast Notifications - Fixed positioning at bottom right */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {activeError && (
          <Toast
            variant="error"
            icon={<AlertCircle />}
            title="Error"
            description={activeError}
          />
        )}
        {actionSuccess && (
          <Toast
            variant="success"
            icon={<CheckCircle />}
            title="Success"
            description={actionSuccess}
          />
        )}
        {createSuccess && (
          <Toast
            variant="success"
            icon={<CheckCircle />}
            title="Success"
            description={createSuccess}
          />
        )}
      </div>
    </>
  );
}

export default AdminUsers;
