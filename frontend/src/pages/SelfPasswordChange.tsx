"use client";

import React from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { ChangePasswordForm } from "@/components/auth/ChangePasswordForm";
import { useTheme } from "@/contexts/ThemeContext";
import interceptLogo from "../assets/Intercept-White.svg?url";
import interceptLogoDark from "../assets/Intercept-Black.svg?url";
import tidemarkLogoDark from "../assets/TMS-logo-black.svg?url";
import tidemarkLogoNeon from "../assets/TMS-logo-green.svg?url";

/**
 * SelfPasswordChange - Voluntary password change page
 * 
 * This page allows authenticated users to proactively change their password
 * for routine security hygiene or in response to suspected compromise.
 * 
 * Reuses ChangePasswordForm component with forced=false to differentiate
 * from mandatory password changes after admin reset.
 */
function SelfPasswordChange() {
  const navigate = useViewTransitionNavigate();
  const { resolvedTheme } = useTheme();
  const passwordChangeLogo = resolvedTheme === "dark" ? interceptLogo : interceptLogoDark;
  const mobileBrandLogo = resolvedTheme === "dark" ? tidemarkLogoNeon : tidemarkLogoDark;

  return (
    <div className="flex h-full w-full flex-col items-start bg-default-background">
      <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start mobile:flex-col mobile:flex-wrap mobile:gap-0">
        <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-6 self-stretch px-12 py-12 mobile:px-0 mobile:py-0">
          <ChangePasswordForm 
            logo={passwordChangeLogo}
            onSuccess={() => navigate("/")}
            forced={false}
          />
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

export default SelfPasswordChange;

