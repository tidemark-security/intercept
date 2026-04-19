"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from "@/components/buttons/Button";
import { OAuthSocialButton } from "@/components/auth/OAuthSocialButton";
import { SignIn } from "@/components/auth/SignIn";
import { TextField } from "@/components/forms/TextField";

import { useSession } from "../contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { ApiError } from "@/types/generated/core/ApiError";
import { OpenAPI } from "@/types/generated/core/OpenAPI";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import interceptLogo from "../assets/Intercept-White.svg?url";
import interceptLogoDark from "../assets/Intercept-Black.svg?url";
import tidemarkLogoDark from "../assets/TMS-logo-black.svg?url";
import tidemarkLogoLight from "../assets/TMS-logo-white.svg?url";
import tidemarkLogoNeon from "../assets/TMS-logo-green.svg?url";

import { ArrowRight, KeyRound } from 'lucide-react';

type LoginStep = "username" | "password";

function Login() {
  const navigate = useViewTransitionNavigate();
  const location = useLocation();
  const { resolvedTheme } = useTheme();
  const { login, loginWithPasskey, status, error, mustChangePassword, resolveError } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<LoginStep>("username");
  const [oidcEnabled, setOidcEnabled] = useState(false);
  const [oidcProviderName, setOidcProviderName] = useState("SSO");
  const [loadingOidcConfig, setLoadingOidcConfig] = useState(true);
  const [oidcError, setOidcError] = useState<string | null>(null);
  const passwordInputRef = React.useRef<HTMLInputElement>(null);
  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const noSso = searchParams.get("no_sso") === "true";
  const isLoading = status === "authenticating";
  const loginLogo = resolvedTheme === "dark" ? interceptLogo : interceptLogoDark;
  const mobileBrandLogo = resolvedTheme === "dark" ? tidemarkLogoNeon : tidemarkLogoDark;
  const desktopBrandLogo = resolvedTheme === "dark" ? tidemarkLogoDark : tidemarkLogoNeon;
  const displayError = error ?? oidcError ?? "";
  const showLocalLogin = !oidcEnabled || noSso;

  // Redirect to home if already authenticated (but not if password change is required)
  useEffect(() => {
    if (status === "authenticated" && !mustChangePassword) {
      navigate("/");
    }
  }, [status, mustChangePassword, navigate]);

  useEffect(() => {
    if (step === "password") {
      passwordInputRef.current?.focus();
    }
  }, [step]);

  useEffect(() => {
    const queryError = searchParams.get("error");
    const message = searchParams.get("message");
    if (queryError === "oidc_failed") {
      setOidcError(message || "Single sign-on failed. Please try again.");
      return;
    }
    setOidcError(null);
  }, [searchParams]);

  useEffect(() => {
    let cancelled = false;

    const loadOidcConfig = async () => {
      try {
        const response = await AuthenticationService.getOidcConfigApiV1AuthOidcConfigGet();
        if (cancelled) {
          return;
        }
        setOidcEnabled(response.enabled);
        setOidcProviderName(response.providerName);
      } catch (err) {
        if (cancelled) {
          return;
        }
        setOidcEnabled(false);
        if (err instanceof ApiError) {
          setOidcError(err.body?.message || "Failed to load sign-in configuration.");
        } else {
          setOidcError("Failed to load sign-in configuration.");
        }
      } finally {
        if (!cancelled) {
          setLoadingOidcConfig(false);
        }
      }
    };

    loadOidcConfig();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleOidcLogin = () => {
    const fromState = location.state as
      | { from?: { pathname?: string; search?: string; hash?: string } }
      | null;
    const destinationPath = fromState?.from?.pathname || "/";
    const destinationSearch = fromState?.from?.search || "";
    const destinationHash = fromState?.from?.hash || "";
    const returnTo = new URL(
      `${destinationPath}${destinationSearch}${destinationHash}`,
      window.location.origin,
    ).toString();
    const apiBase = OpenAPI.BASE || window.location.origin;
    const oidcUrl = new URL("/api/v1/auth/oidc/login", apiBase);
    oidcUrl.searchParams.set("next", returnTo);
    window.location.assign(oidcUrl.toString());
  };

  const handleSubmit = async (event?: React.MouseEvent<HTMLButtonElement>) => {
    if (event) {
      event.preventDefault();
    }
    resolveError();
    setOidcError(null);

    if (!username.trim() || !password.trim()) {
      return;
    }

    await login({ username: username.trim(), password });
  };

  const handleContinue = async (event?: React.MouseEvent<HTMLButtonElement>) => {
    if (event) {
      event.preventDefault();
    }
    resolveError();
    setOidcError(null);

    if (!username.trim()) {
      return;
    }

    const passkeyResult = await loginWithPasskey(username.trim());
    if (passkeyResult === "password_required") {
      setStep("password");
      return;
    }

    if (passkeyResult === "cancelled") {
      setStep("username");
    }
  };

  const handleKeyPress = async (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
      if (step === "username") {
        await handleContinue();
        return;
      }
      await handleSubmit();
    }
  };

  return (
    <div className="flex h-full w-full flex-col items-start bg-default-background">
      <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start mobile:flex-col mobile:flex-wrap mobile:gap-0">
        <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-6 self-stretch px-12 py-12 mobile:px-0 mobile:py-0">
          <div className="hidden w-full flex-wrap items-start justify-center mobile:flex">
            <img
              className="h-36 flex-none object-cover"
              src={mobileBrandLogo}
            />
          </div>
          {mustChangePassword ? (
            <ChangePasswordForm logo={loginLogo} onSuccess={() => navigate("/")} />
          ) : loadingOidcConfig ? (
            <div className="flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6">
              <img className="flex-none" src={loginLogo} />
              <div className="flex w-full flex-col items-center justify-center gap-4">
                <hr className={resolvedTheme === "dark" ? "w-full border-brand-primary" : "w-full border-neutral-1000"} />
                <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
                  Loading sign-in options
                </span>
                <p className="w-full text-body font-body text-subtext-color">
                  Checking authentication configuration...
                </p>
                <hr className={resolvedTheme === "dark" ? "w-full border-brand-primary" : "w-full border-neutral-1000"} />
              </div>
            </div>
          ) : !showLocalLogin ? (
            <div className="flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6">
              <img className="flex-none" src={loginLogo} />
              <div className="flex w-full flex-col items-center justify-center gap-4">
                <hr className={resolvedTheme === "dark" ? "w-full border-brand-primary" : "w-full border-neutral-1000"} />
                <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
                  External sign in
                </span>
                <div className="flex w-full flex-col gap-2">
                  <OAuthSocialButton
                    className="h-10 w-full flex-none"
                    onClick={() => handleOidcLogin()}
                    disabled={isLoading}
                  >
                    {isLoading ? "Redirecting..." : `Sign in with ${oidcProviderName}`}
                  </OAuthSocialButton>
                  {displayError ? (
                    <p className="text-caption font-caption text-error-500">{displayError}</p>
                  ) : null}
                </div>
                <hr className={resolvedTheme === "dark" ? "w-full border-brand-primary" : "w-full border-neutral-1000"} />
              </div>
            </div>
          ) : (
            <SignIn
              logo={loginLogo}
              enableExternal={false}
            emailField={
              <TextField
                className="h-auto w-full flex-none"
                label="Username"
                  helpText={step === "username" ? displayError : ""}
                  error={step === "username" && !!displayError}
              >
                <TextField.Input
                  placeholder="Enter your username"
                  value={username}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                    setUsername(event.target.value);
                      if (error) resolveError();
                      if (oidcError) setOidcError(null);
                  }}
                  onKeyPress={handleKeyPress}
                  disabled={isLoading}
                />
              </TextField>
            }
            passwordField={
              step === "password" ? (
                <TextField
                  className="h-auto w-full flex-none"
                  label="Password"
                  helpText={displayError}
                  error={!!displayError}
                >
                  <TextField.Input
                    ref={passwordInputRef}
                    type="password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                      setPassword(event.target.value);
                      if (error) resolveError();
                      if (oidcError) setOidcError(null);
                    }}
                    onKeyPress={handleKeyPress}
                    disabled={isLoading}
                  />
                </TextField>
              ) : null
            }
            submitButton={
              step === "username" ? (
                <Button
                  className="h-10 w-full flex-none"
                  variant="neutral-secondary"
                  size="large"
                  icon={<ArrowRight />}
                  onClick={handleContinue}
                  disabled={isLoading || !username.trim()}
                >
                  {isLoading ? "Checking sign-in options..." : "Continue"}
                </Button>
              ) : (
                <Button
                  className="h-10 w-full flex-none"
                  variant="neutral-secondary"
                  size="large"
                  icon={<KeyRound />}
                  onClick={handleSubmit}
                  disabled={isLoading || !username.trim() || !password.trim()}
                >
                  {isLoading ? "Signing in..." : "Sign in"}
                </Button>
              )
            }
          />
          )}
        </div>
        <div className={`flex grow shrink-0 basis-0 flex-col items-center gap-12 self-stretch px-12 py-12 mobile:hidden ${resolvedTheme === "dark" ? "bg-brand-primary" : "bg-neutral-1000"}`}>
          <div className="flex w-full max-w-[448px] grow shrink-0 basis-0 flex-col items-center justify-center gap-8">
            <div className="flex w-full flex-col items-center gap-6">
              <img
                className="w-full flex-none"
                src={desktopBrandLogo}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;