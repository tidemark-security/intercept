import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import type { app__api__routes__auth__UserSummary as AuthUserSummary } from "@/types/generated/models/app__api__routes__auth__UserSummary";
import type { SessionSummary } from "@/types/generated/models/SessionSummary";
import type { LoginRequest } from "@/types/generated/models/LoginRequest";

type UserSummary = AuthUserSummary;

export interface LockoutResponse {
  retryAfterSeconds?: number;
  reason?: string;
}

export type PasskeyLoginResult = "authenticated" | "password_required" | "cancelled" | "failed";

export type SessionStatus = "initializing" | "unauthenticated" | "authenticating" | "authenticated" | "locked";

export interface SessionState {
  status: SessionStatus;
  user: UserSummary | null;
  session: SessionSummary | null;
  mustChangePassword: boolean;
  lockout: LockoutResponse | null;
  error: string | null;
}

export const sessionInitialState: SessionState = {
  status: "initializing",
  user: null,
  session: null,
  mustChangePassword: false,
  lockout: null,
  error: null,
};

export type SessionAction =
  | { type: "START_AUTH" }
  | {
      type: "SET_AUTHENTICATED";
      payload: {
        user: UserSummary;
        session: SessionSummary;
        mustChangePassword?: boolean;
      };
    }
  | { type: "SET_UNAUTHENTICATED" }
  | { type: "SET_ERROR"; payload: string }
  | { type: "CLEAR_ERROR" }
  | { type: "SET_LOCKOUT"; payload: LockoutResponse }
  | { type: "CLEAR_LOCKOUT" }
  | { type: "SET_MUST_CHANGE_PASSWORD"; payload: boolean };

export interface SessionContextValue extends SessionState {
  login: (
    credentials: LoginRequest,
    options?: { remember?: boolean }
  ) => Promise<void>;
  loginWithPasskey: (username: string) => Promise<PasskeyLoginResult>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  resolveError: () => void;
  acknowledgeLockout: () => void;
  setMustChangePassword: (value: boolean) => void;
  // Role-based access helpers
  isAdmin: boolean;
  isAnalyst: boolean;
  isAuditor: boolean;
}
export const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export interface SessionProviderProps {
  children: ReactNode;
}

export const useSession = () => {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }

  return context;
};
