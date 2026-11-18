import type { UserRole } from "@/types/generated/models/UserRole";

export const API_KEY_SCOPE_OPTIONS = [
  {
    value: "api:read",
    label: "Read API",
    description: "Read application data through REST endpoints.",
  },
  {
    value: "api:write",
    label: "Write API",
    description: "Create, change, and delete application data.",
  },
  {
    value: "api:admin",
    label: "Admin API",
    description: "Use administrator-only REST endpoints.",
  },
  {
    value: "mcp:access",
    label: "MCP access",
    description: "Authenticate directly to the Intercept MCP server.",
  },
] as const;

export type ApiKeyScope = (typeof API_KEY_SCOPE_OPTIONS)[number]["value"];

export function allowedApiKeyScopesForRole(
  role: UserRole | string | undefined,
): ApiKeyScope[] {
  if (role === "ADMIN") {
    return API_KEY_SCOPE_OPTIONS.map((option) => option.value);
  }
  if (role === "AUDITOR") {
    return ["api:read", "mcp:access"];
  }
  return ["api:read", "api:write", "mcp:access"];
}
