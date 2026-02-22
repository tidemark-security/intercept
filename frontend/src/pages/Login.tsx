"use client";

import React, { useState, useEffect } from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from "@/components/buttons/Button";
import { OAuthSocialButton } from "@/components/auth/OAuthSocialButton";
import { SignIn } from "@/components/auth/SignIn";
import { TextField } from "@/components/forms/TextField";

import { useSession } from "../contexts/sessionContext";
import { useTheme } from "@/contexts/ThemeContext";
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import interceptLogo from "../assets/Intercept-White.svg?url";
import interceptLogoDark from "../assets/Intercept-Black.svg?url";
import googleLogo from "../assets/google-logo.svg?url";
import microsoftLogo from "../assets/microsoft-logo.jpg";
import tidemarkLogoDark from "../assets/TMS-logo-black.svg?url";
import tidemarkLogoNeon from "../assets/TMS-logo-green.svg?url";

import { ArrowRight, KeyRound } from 'lucide-react';

type LoginStep = "username" | "password";

function Login() {
  const navigate = useViewTransitionNavigate();
  const { resolvedTheme } = useTheme();
  const { login, loginWithPasskey, status, error, mustChangePassword, resolveError } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<LoginStep>("username");

  // Redirect to home if already authenticated (but not if password change is required)
  useEffect(() => {
    if (status === "authenticated" && !mustChangePassword) {
      navigate("/");
    }
  }, [status, mustChangePassword, navigate]);

  const handleSubmit = async (event?: React.MouseEvent<HTMLButtonElement>) => {
    if (event) {
      event.preventDefault();
    }
    resolveError();

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

  const isLoading = status === "authenticating";
  const loginLogo = resolvedTheme === "dark" ? interceptLogo : interceptLogoDark;
  const mobileBrandLogo = resolvedTheme === "dark" ? tidemarkLogoNeon : tidemarkLogoDark;

  return (
    <div className="flex h-full w-full flex-col items-start bg-default-background">
      <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start mobile:flex-col mobile:flex-wrap mobile:gap-0">
        <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-6 self-stretch px-12 py-12 mobile:px-0 mobile:py-0">
          {mustChangePassword ? (
            <ChangePasswordForm logo={loginLogo} onSuccess={() => navigate("/")} />
          ) : (
            <SignIn
              logo={loginLogo}
              externalSignInOptions={
              <>
                <OAuthSocialButton
                  className="h-10 w-full flex-none"
                  onClick={(event: React.MouseEvent<HTMLButtonElement>) => {}}
                  disabled={true}
                >
                  Sign in with SSO
                </OAuthSocialButton>
                <OAuthSocialButton
                  className="h-10 w-full flex-none"
                  logo={googleLogo}
                  onClick={(event: React.MouseEvent<HTMLButtonElement>) => {}}
                  disabled={true}
                >
                  Sign in with Google
                </OAuthSocialButton>
                <OAuthSocialButton
                  className="h-10 w-full flex-none"
                  logo={microsoftLogo}
                  onClick={(event: React.MouseEvent<HTMLButtonElement>) => {}}
                  disabled={true}
                >
                  Sign in with Microsoft
                </OAuthSocialButton>
              </>
            }
            emailField={
              <TextField
                className="h-auto w-full flex-none"
                label="Username"
                helpText={step === "username" ? (error ?? "") : ""}
                error={step === "username" && !!error}
              >
                <TextField.Input
                  placeholder="Enter your username"
                  value={username}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                    setUsername(event.target.value);
                    if (error) resolveError();
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
                  helpText={error ?? ""}
                  error={!!error}
                >
                  <TextField.Input
                    type="password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                      setPassword(event.target.value);
                      if (error) resolveError();
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
          <div className="hidden w-full flex-wrap items-start justify-center mobile:flex">
            <img
              className="h-52 flex-none object-cover"
              src={mobileBrandLogo}
            />
          </div>
        </div>
        <div className="flex grow shrink-0 basis-0 flex-col items-center gap-12 self-stretch bg-brand-primary px-12 py-12 mobile:hidden">
          <div className="flex w-full max-w-[448px] grow shrink-0 basis-0 flex-col items-center justify-center gap-8">
            <div className="flex w-full flex-col items-center gap-6">
              <img
                className="w-full flex-none"
                src={tidemarkLogoDark}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;