import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import {
  ArrowRight,
  Check,
  ChevronRight,
  ExternalLink,
  Link2,
  X,
} from "lucide-react";

import { AuthSplitLayout } from "@/components/auth";
import { Button } from "@/components/buttons/Button";
import { Badge } from "@/components/data-display/Badge";
import { Alert } from "@/components/feedback/Alert";
import { useTheme } from "@/contexts/ThemeContext";
import interceptLogo from "../assets/Intercept-White.svg?url";
import interceptLogoDark from "../assets/Intercept-Black.svg?url";

interface McpConsentContext {
  transaction_id: string;
  csrf_token: string;
  client_name: string;
  client_id: string;
  client_uri: string | null;
  redirect_uri: string;
  scopes: string[];
  verified_domain: string | null;
}

// This capability-bearing endpoint is intentionally hidden from OpenAPI. Keep
// this runtime guard in lockstep with OIDCConsentContext in mcp_oauth.py.

function isConsentContext(value: unknown): value is McpConsentContext {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.transaction_id === "string" &&
    typeof candidate.csrf_token === "string" &&
    typeof candidate.client_name === "string" &&
    typeof candidate.client_id === "string" &&
    (candidate.client_uri === null || typeof candidate.client_uri === "string") &&
    typeof candidate.redirect_uri === "string" &&
    Array.isArray(candidate.scopes) &&
    candidate.scopes.every((scope) => typeof scope === "string") &&
    (candidate.verified_domain === null ||
      typeof candidate.verified_domain === "string")
  );
}

function safeExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function ConsentDetails({ context }: { context: McpConsentContext }) {
  const { resolvedTheme } = useTheme();
  const clientWebsite = safeExternalUrl(context.client_uri);
  const rows = [
    ["Application", context.client_name],
    ["Application ID", context.client_id],
    ["Callback URI", context.redirect_uri],
    ["Requested scope", context.scopes.join(", ") || "None"],
  ];

  return (
    <details className="group w-full border-y border-neutral-border py-2">
      <summary className="flex cursor-pointer list-none items-center gap-2 py-2 text-caption-bold font-caption-bold text-subtext-color hover:text-default-font focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-border focus-visible:text-default-font">
        <ChevronRight className="transition-transform group-open:rotate-90" />
        Connection details
      </summary>
      <dl className="mt-2 flex flex-col border border-neutral-border bg-neutral-50 px-4 py-2">
        {rows.map(([label, value]) => (
          <div
            className="grid grid-cols-[128px_minmax(0,1fr)] gap-4 border-b border-neutral-border py-2 last:border-b-0 mobile:grid-cols-1 mobile:gap-1"
            key={label}
          >
            <dt className="text-caption-bold font-caption-bold text-subtext-color">
              {label}
            </dt>
            <dd className="break-all text-monospace-body font-monospace-body text-default-font">
              {value}
            </dd>
          </div>
        ))}
        {clientWebsite ? (
          <div className="grid grid-cols-[128px_minmax(0,1fr)] gap-4 py-2 mobile:grid-cols-1 mobile:gap-1">
            <dt className="text-caption-bold font-caption-bold text-subtext-color">
              Website
            </dt>
            <dd>
              <a
                className={`inline-flex items-center gap-1 break-all text-body font-body underline underline-offset-2 ${
                  resolvedTheme === "dark"
                    ? "text-brand-primary"
                    : "text-brand-800"
                }`}
                href={clientWebsite}
                rel="noreferrer"
                target="_blank"
              >
                {clientWebsite}
                <ExternalLink />
              </a>
            </dd>
          </div>
        ) : null}
      </dl>
    </details>
  );
}

function McpConsent() {
  const location = useLocation();
  const { resolvedTheme } = useTheme();
  const [context, setContext] = useState<McpConsentContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const transactionId = useMemo(
    () => new URLSearchParams(location.hash.replace(/^#/, "")).get("txn_id"),
    [location.hash],
  );
  const loginLogo = resolvedTheme === "dark" ? interceptLogo : interceptLogoDark;

  useEffect(() => {
    let cancelled = false;
    setContext(null);
    setError(null);
    if (!transactionId) {
      setError("This MCP authorization request is invalid or incomplete.");
      return;
    }

    const loadContext = async () => {
      try {
        const response = await fetch(
          "/api/v1/mcp/oauth/consent/oidc",
          {
            method: "POST",
            credentials: "omit",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ transaction_id: transactionId }),
          },
        );
        const payload: unknown = await response.json();
        if (!response.ok || !isConsentContext(payload)) {
          const detail =
            payload && typeof payload === "object" && "detail" in payload
              ? String((payload as { detail: unknown }).detail)
              : "This MCP authorization request is no longer available.";
          throw new Error(detail);
        }
        if (!cancelled) setContext(payload);
      } catch (reason) {
        if (!cancelled) {
          setError(
            reason instanceof Error
              ? reason.message
              : "This MCP authorization request could not be loaded.",
          );
        }
      }
    };

    void loadContext();
    return () => {
      cancelled = true;
    };
  }, [transactionId]);

  return (
    <AuthSplitLayout>
      <section className="flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6">
        <img alt="Tidemark Intercept" className="flex-none" src={loginLogo} />
        <div className="flex w-full flex-col items-center justify-center gap-4">
          <hr
            className={
              resolvedTheme === "dark"
                ? "w-full border-brand-primary"
                : "w-full border-neutral-1000"
            }
          />
          <h1 className="w-full text-heading-2 font-heading-2 text-subtext-color">
            Authorize MCP access
          </h1>

          {error ? (
            <Alert
              variant="error"
              icon={<X />}
              title="Authorization unavailable"
              description={error}
            />
          ) : !context ? (
            <Alert
              variant="neutral"
              icon={<Link2 />}
              title="Loading connection request"
              description="Retrieving the MCP client and callback details."
            />
          ) : (
            <>
              <Alert
                variant="neutral"
                icon={<Link2 />}
                title={`${context.client_name} wants to connect`}
                description="This client will act through your Intercept identity. Approve only if you started and recognize this connection."
              />

              {context.verified_domain ? (
                <Badge className="self-start" variant="success" icon={<Check />}>
                  Verified domain: {context.verified_domain}
                </Badge>
              ) : null}

              <div className="flex w-full flex-col gap-2 border border-warning-200 bg-warning-50 p-4">
                <span className="text-caption-bold font-caption-bold text-warning-900">
                  Credentials will be returned to
                </span>
                <code className="break-all text-monospace-body font-monospace-body text-warning-1000">
                  {context.redirect_uri}
                </code>
              </div>

              <ConsentDetails context={context} />

              <form
                action="/mcp/consent"
                className="flex w-full flex-col items-center justify-center gap-3"
                method="post"
              >
                <input
                  name="txn_id"
                  type="hidden"
                  value={context.transaction_id}
                />
                <input
                  name="csrf_token"
                  type="hidden"
                  value={context.csrf_token}
                />
                <input name="submit" type="hidden" value="true" />
                <Button
                  className="h-10 w-full flex-none"
                  iconRight={<ArrowRight />}
                  name="action"
                  size="large"
                  type="submit"
                  value="approve"
                  variant="brand-primary"
                >
                  Authorize
                </Button>
                <Button
                  className="h-10 w-full flex-none"
                  icon={<X />}
                  name="action"
                  size="large"
                  type="submit"
                  value="deny"
                  variant="neutral-secondary"
                >
                  Deny
                </Button>
              </form>
            </>
          )}
          <hr
            className={
              resolvedTheme === "dark"
                ? "w-full border-brand-primary"
                : "w-full border-neutral-1000"
            }
          />
        </div>
      </section>
    </AuthSplitLayout>
  );
}

export default McpConsent;
