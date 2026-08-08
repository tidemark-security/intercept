import type { ReactNode } from "react";

import { useTheme } from "@/contexts/ThemeContext";
import tidemarkLogoDark from "@/assets/TMS-logo-black.svg?url";
import tidemarkLogoNeon from "@/assets/TMS-logo-green.svg?url";

interface AuthSplitLayoutProps {
  children: ReactNode;
}

/** The shared Intercept authentication shell used by login-adjacent flows. */
export function AuthSplitLayout({ children }: AuthSplitLayoutProps) {
  const { resolvedTheme } = useTheme();
  const mobileBrandLogo =
    resolvedTheme === "dark" ? tidemarkLogoNeon : tidemarkLogoDark;
  const desktopBrandLogo =
    resolvedTheme === "dark" ? tidemarkLogoDark : tidemarkLogoNeon;

  return (
    <div className="flex h-full w-full flex-col items-start bg-default-background">
      <div className="flex w-full grow shrink-0 basis-0 flex-wrap items-start mobile:flex-col mobile:flex-wrap mobile:gap-0">
        <main className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-6 self-stretch px-12 py-12 mobile:px-0 mobile:py-0">
          <div className="hidden w-full flex-wrap items-start justify-center mobile:flex">
            <img
              alt="Tidemark Security"
              className="h-36 flex-none object-cover"
              src={mobileBrandLogo}
            />
          </div>
          {children}
        </main>

        <aside
          className={`flex grow shrink-0 basis-0 flex-col items-center gap-12 self-stretch px-12 py-12 mobile:hidden ${
            resolvedTheme === "dark" ? "bg-brand-primary" : "bg-neutral-1000"
          }`}
        >
          <div className="flex w-full max-w-[448px] grow shrink-0 basis-0 flex-col items-center justify-center gap-8">
            <div className="flex w-full flex-col items-center gap-6">
              <img
                alt="Tidemark Security"
                className="w-full flex-none"
                src={desktopBrandLogo}
              />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
