"use client";

import React, { useState } from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from "@/components/buttons/Button";
import { TextField } from "@/components/forms/TextField";

import { useSession } from "@/contexts/sessionContext";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import { ApiError } from "@/types/generated/core/ApiError";

import { AlertCircle, Lock, LogOut } from 'lucide-react';
interface ChangePasswordFormProps {
  logo?: string;
  onSuccess?: () => void;
  forced?: boolean; // True for forced changes (after admin reset), false for voluntary changes
}

export function ChangePasswordForm({ logo, onSuccess, forced = true }: ChangePasswordFormProps) {
  const navigate = useViewTransitionNavigate();
  const { setMustChangePassword, logout } = useSession();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const validatePassword = (password: string): string | null => {
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
  };

  const handleSubmit = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setError(null);
    
    // Validate fields
    if (!currentPassword.trim()) {
      setError("Current password is required");
      return;
    }
    
    if (!newPassword.trim()) {
      setError("New password is required");
      return;
    }
    
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match");
      return;
    }
    
    // Validate new password policy
    const validationError = validatePassword(newPassword);
    if (validationError) {
      setError(validationError);
      return;
    }
    
    setIsSubmitting(true);
    
    try {
      await AuthenticationService.changePasswordApiV1AuthPasswordChangePost({
        requestBody: {
          currentPassword: currentPassword,
          newPassword: newPassword,
        },
      });
      
      setSuccess(true);
      setMustChangePassword(false);
      
      // Wait a moment then redirect
      setTimeout(() => {
        if (onSuccess) {
          onSuccess();
        } else {
          navigate("/");
        }
      }, 2000);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError("Current password is incorrect");
        } else if (err.status === 400) {
          setError(err.body?.message || "Password does not meet requirements");
        } else {
          setError("An error occurred while changing your password");
        }
      } else {
        setError("An unexpected error occurred");
      }
      setIsSubmitting(false);
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !isSubmitting) {
      handleSubmit(event as any);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="flex w-full max-w-[448px] flex-col items-center justify-center gap-8 rounded-md px-6 py-6">
      {logo ? <img className="flex-none" src={logo} /> : null}
      
      <div className="flex w-full flex-col items-center justify-center gap-4">
        <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
        <span className="w-full text-heading-2 font-heading-2 text-subtext-color">
          {forced ? "Change Password Required" : "Change Password"}
        </span>

        {/* Warning Banner - only show for forced changes */}
        {forced && (
          <div className="flex w-full items-center gap-2 rounded-md bg-warning-50 px-3 py-2">
            <AlertCircle className="h-4 w-4 flex-none text-warning-600" />
            <p className="text-caption font-caption text-warning-700">
              You must change your password to continue
            </p>
          </div>
        )}

        {/* Success Message */}
        {success && (
          <div className="flex w-full items-center gap-2 rounded-md bg-success-50 px-4 py-3">
            <p className="text-body font-body text-success-700">
              Password changed successfully! Redirecting...
            </p>
          </div>
        )}

        {/* Form Fields */}
        {!success && (
          <>
            <div className="flex w-full flex-col items-start justify-center gap-2">
              <TextField
                className="h-auto w-full flex-none"
                label=""
                helpText={error || ""}
                error={!!error}
              >
                <TextField.Input
                  type="password"
                  placeholder="Enter your current password"
                  value={currentPassword}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                    setCurrentPassword(event.target.value);
                    if (error) setError(null);
                  }}
                  onKeyPress={handleKeyPress}
                  disabled={isSubmitting}
                />
              </TextField>
            </div>

            <div className="flex w-full flex-col items-start justify-center gap-2">
              <TextField
                className="h-auto w-full flex-none"
                label=""
                helpText="Minimum 12 characters with uppercase, lowercase, number, and special character"
              >
                <TextField.Input
                  type="password"
                  placeholder="Enter your new password"
                  value={newPassword}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                    setNewPassword(event.target.value);
                    if (error) setError(null);
                  }}
                  onKeyPress={handleKeyPress}
                  disabled={isSubmitting}
                />
              </TextField>
            </div>

            <div className="flex w-full flex-col items-start justify-center gap-2">
              <TextField
                className="h-auto w-full flex-none"
                label=""
              >
                <TextField.Input
                  type="password"
                  placeholder="Re-enter your new password"
                  value={confirmPassword}
                  onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
                    setConfirmPassword(event.target.value);
                    if (error) setError(null);
                  }}
                  onKeyPress={handleKeyPress}
                  disabled={isSubmitting}
                />
              </TextField>
            </div>

            <div className="flex w-full flex-col items-center justify-center gap-8">
              <Button
                className="h-10 w-full flex-none"
                variant="neutral-secondary"
                size="large"
                icon={<Lock />}
                onClick={handleSubmit}
                disabled={
                  isSubmitting ||
                  !currentPassword.trim() ||
                  !newPassword.trim() ||
                  !confirmPassword.trim()
                }
              >
                {isSubmitting ? "Changing Password..." : "Change Password"}
              </Button>

              {forced ? (
                <Button
                  className="h-10 w-full flex-none"
                  variant="neutral-tertiary"
                  size="large"
                  icon={<LogOut />}
                  onClick={handleLogout}
                  disabled={isSubmitting}
                >
                  Logout
                </Button>
              ) : (
                <Button
                  className="h-10 w-full flex-none"
                  variant="neutral-tertiary"
                  size="large"
                  onClick={() => navigate(-1)}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
              )}
            </div>
          </>
        )}

        <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-brand-primary" />
      </div>
    </div>
  );
}
