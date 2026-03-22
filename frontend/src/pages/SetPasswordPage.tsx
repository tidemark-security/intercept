import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Button } from "@/components/buttons/Button";
import { TextField } from "@/components/forms/TextField";
import { useTheme } from "@/contexts/ThemeContext";
import { useViewTransitionNavigate } from "@/hooks/useViewTransitionNavigate";
import { ApiError } from "@/types/generated/core/ApiError";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import interceptLogo from "../assets/Intercept-White.svg?url";
import interceptLogoDark from "../assets/Intercept-Black.svg?url";
import tidemarkLogoDark from "../assets/TMS-logo-black.svg?url";
import tidemarkLogoNeon from "../assets/TMS-logo-green.svg?url";
import { AlertCircle, CheckCircle, KeyRound } from "lucide-react";

function validatePassword(password: string): string | null {
  if (password.length < 12) {
    return "Password must be at least 12 characters long";
  }
  if (!/[A-Z]/.test(password)) {
    return "Password must include at least one uppercase letter";
  }
  if (!/[a-z]/.test(password)) {
    return "Password must include at least one lowercase letter";
  }
  if (!/[0-9]/.test(password)) {
    return "Password must include at least one number";
  }
  if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
    return "Password must include at least one special character";
  }
  return null;
}

export default function SetPasswordPage() {
  const navigate = useViewTransitionNavigate();
  const { resolvedTheme } = useTheme();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token")?.trim() ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loginLogo = resolvedTheme === "dark" ? interceptLogo : interceptLogoDark;
  const mobileBrandLogo = resolvedTheme === "dark" ? tidemarkLogoNeon : tidemarkLogoDark;

  useEffect(() => {
    if (success) {
      const timer = window.setTimeout(() => navigate("/login"), 1500);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [success, navigate]);

  const passwordHelpText = useMemo(() => {
    if (error && !success) {
      return error;
    }
    return "Minimum 12 characters with uppercase, lowercase, number, and special character";
  }, [error, success]);

  const handleSubmit = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("Password reset token is missing");
      return;
    }
    if (!newPassword.trim()) {
      setError("New password is required");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    const validationError = validatePassword(newPassword);
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      setIsSubmitting(true);
      await AuthenticationService.resetPasswordWithTokenApiV1AuthResetPasswordPost({
        requestBody: {
          token,
          newPassword,
        },
      });
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.body?.message || "Unable to set password with this link");
      } else {
        setError("Unable to set password with this link");
      }
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex h-full w-full flex-col items-start bg-default-background">
      <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start mobile:flex-col mobile:flex-wrap mobile:gap-0">
        <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-6 self-stretch px-12 py-12 mobile:px-0 mobile:py-0">
          <div className="hidden w-full flex-wrap items-start justify-center mobile:flex">
            <img className="h-36 flex-none object-cover" src={mobileBrandLogo} />
          </div>

          <div className="flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6">
            <img className="flex-none" src={loginLogo} />
            <div className="flex w-full flex-col items-center justify-center gap-4">
              <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
              <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
                Set Your Password
              </span>

              {success ? (
                <div className="flex w-full items-center gap-2 rounded-md bg-success-50 px-4 py-3">
                  <CheckCircle className="h-4 w-4 flex-none text-success-700" />
                  <p className="text-body font-body text-success-700">
                    Password set successfully. Redirecting to sign in...
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex w-full items-center gap-2 rounded-md bg-warning-50 px-3 py-2">
                    <KeyRound className="h-4 w-4 flex-none text-warning-700" />
                    <p className="text-caption font-caption text-warning-700">
                      This link can only be used once before it expires.
                    </p>
                  </div>

                  {!token ? (
                    <div className="flex w-full items-center gap-2 rounded-md bg-error-50 px-4 py-3">
                      <AlertCircle className="h-4 w-4 flex-none text-error-700" />
                      <p className="text-body font-body text-error-700">
                        Password reset token is missing from the URL.
                      </p>
                    </div>
                  ) : null}

                  <div className="flex w-full flex-col items-start justify-center gap-2">
                    <TextField
                      className="h-auto w-full flex-none"
                      label=""
                      helpText={passwordHelpText}
                      error={Boolean(error)}
                    >
                      <TextField.Input
                        type="password"
                        placeholder="Enter your new password"
                        value={newPassword}
                        onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                          setNewPassword(event.target.value);
                          if (error) setError(null);
                        }}
                        disabled={isSubmitting || !token}
                      />
                    </TextField>
                  </div>

                  <div className="flex w-full flex-col items-start justify-center gap-2">
                    <TextField className="h-auto w-full flex-none" label="">
                      <TextField.Input
                        type="password"
                        placeholder="Re-enter your new password"
                        value={confirmPassword}
                        onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                          setConfirmPassword(event.target.value);
                          if (error) setError(null);
                        }}
                        disabled={isSubmitting || !token}
                      />
                    </TextField>
                  </div>

                  <div className="flex w-full flex-col items-center justify-center gap-3">
                    <Button
                      className="h-10 w-full flex-none"
                      onClick={handleSubmit}
                      loading={isSubmitting}
                      disabled={!token}
                    >
                      Set Password
                    </Button>
                    <Button
                      className="h-10 w-full flex-none"
                      variant="neutral-secondary"
                      onClick={() => navigate("/login")}
                      disabled={isSubmitting}
                    >
                      Back to Sign In
                    </Button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}