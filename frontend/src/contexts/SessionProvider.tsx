import React, { useEffect, useMemo, useReducer } from "react";
import { ApiError } from "@/types/generated/core/ApiError";
import { AuthenticationService } from "@/types/generated/services/AuthenticationService";
import { browserSupportsPasskeys, getPasskeyAssertion } from "@/utils/webauthn";
import {
  LockoutResponse,
  PasskeyLoginResult,
  SessionContext,
  SessionContextValue,
  SessionProviderProps,
  SessionState,
  SessionAction,
  sessionInitialState,
} from "./sessionContext";

const sessionReducer = (state: SessionState, action: SessionAction): SessionState => {
  switch (action.type) {
    case "START_AUTH":
      return {
        ...state,
        status: "authenticating",
        error: null,
      };
    case "SET_AUTHENTICATED":
      return {
        status: "authenticated",
        user: action.payload.user,
        session: action.payload.session,
        mustChangePassword: Boolean(action.payload.mustChangePassword),
        lockout: null,
        error: null,
      };
    case "SET_UNAUTHENTICATED":
      return {
        ...sessionInitialState,
        status: "unauthenticated",
        error: state.error, // Preserve error message for display
      };
    case "SET_ERROR":
      return {
        ...state,
        error: action.payload,
      };
    case "CLEAR_ERROR":
      return {
        ...state,
        error: null,
      };
    case "SET_LOCKOUT":
      return {
        ...state,
        status: "locked",
        lockout: action.payload,
      };
    case "CLEAR_LOCKOUT":
      return {
        ...state,
        lockout: null,
      };
    case "SET_MUST_CHANGE_PASSWORD":
      return {
        ...state,
        mustChangePassword: action.payload,
      };
    default:
      return state;
  }
};

export const SessionProvider = ({ children }: SessionProviderProps) => {
  const [state, dispatch] = useReducer(sessionReducer, sessionInitialState);

  useEffect(() => {
    const validateSession = async () => {
      try {
        const response = await AuthenticationService.getSessionApiV1AuthSessionGet();

        dispatch({
          type: "SET_AUTHENTICATED",
          payload: {
            user: response.user,
            session: response.session,
            mustChangePassword: response.mustChangePassword || false,
          },
        });
      } catch (error) {
        dispatch({ type: "SET_UNAUTHENTICATED" });
      }
    };

    validateSession();
  }, []);

  const actions = useMemo(() => {
    return {
      async login(credentials) {
        dispatch({ type: "START_AUTH" });
        try {
          const response = await AuthenticationService.loginApiV1AuthLoginPost({
            requestBody: credentials,
          });

          dispatch({
            type: "SET_AUTHENTICATED",
            payload: {
              user: response.user,
              session: response.session,
              mustChangePassword: response.mustChangePassword,
            },
          });
        } catch (error) {
          if (error instanceof ApiError) {
            if (error.status === 423) {
              dispatch({
                type: "SET_ERROR",
                payload: "Unable to sign in with the provided credentials.",
              });
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return;
            }

            if (error.status === 401) {
              dispatch({
                type: "SET_ERROR",
                payload: "Unable to sign in with the provided credentials.",
              });
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return;
            }

            if (error.status === 403) {
              dispatch({
                type: "SET_ERROR",
                payload: "Unable to sign in with the provided credentials.",
              });
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return;
            }

            if (error.status === 429) {
              dispatch({
                type: "SET_ERROR",
                payload: "Too many login attempts. Please try again later.",
              });
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return;
            }

            dispatch({
              type: "SET_ERROR",
              payload: error.body?.message || "Login failed. Please try again.",
            });
          } else {
            dispatch({
              type: "SET_ERROR",
              payload: "An unexpected error occurred. Please try again.",
            });
          }
          dispatch({ type: "SET_UNAUTHENTICATED" });
        }
      },
      async loginWithPasskey(username: string): Promise<PasskeyLoginResult> {
        dispatch({ type: "START_AUTH" });
        try {
          if (!browserSupportsPasskeys()) {
            dispatch({ type: "SET_ERROR", payload: "Passkey sign-in is unavailable on this browser." });
            dispatch({ type: "SET_UNAUTHENTICATED" });
            return "failed";
          }

          const begin = await AuthenticationService.beginPasskeyAuthenticationApiV1AuthPasskeysAuthenticateOptionsPost({
            requestBody: { username },
          });

          let credential: Record<string, unknown>;
          try {
            credential = await getPasskeyAssertion(begin.options);
          } catch (passkeyError) {
            if (
              (passkeyError instanceof DOMException && passkeyError.name === "AbortError")
              || (passkeyError instanceof Error && passkeyError.message.toLowerCase().includes("cancelled"))
            ) {
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return "cancelled";
            }
            throw passkeyError;
          }

          const response = await AuthenticationService.finishPasskeyAuthenticationApiV1AuthPasskeysAuthenticateVerifyPost({
            requestBody: {
              challenge: begin.challenge,
              credential,
            },
          });

          dispatch({
            type: "SET_AUTHENTICATED",
            payload: {
              user: response.user,
              session: response.session,
              mustChangePassword: response.mustChangePassword,
            },
          });
          return "authenticated";
        } catch (error) {
          if (error instanceof ApiError) {
            if (error.status === 404) {
              dispatch({ type: "CLEAR_ERROR" });
              dispatch({ type: "SET_UNAUTHENTICATED" });
              return "password_required";
            }
            dispatch({
              type: "SET_ERROR",
              payload: "Passkey sign-in failed. Please try again.",
            });
          } else if (error instanceof Error) {
            dispatch({ type: "SET_ERROR", payload: "Passkey sign-in failed. Please try again." });
          } else {
            dispatch({ type: "SET_ERROR", payload: "Passkey sign-in failed. Please try again." });
          }
          dispatch({ type: "SET_UNAUTHENTICATED" });
          return "failed";
        }
      },
      async logout() {
        try {
          await AuthenticationService.logoutApiV1AuthLogoutPost();
        } catch (error) {
          console.error("Logout error:", error);
        } finally {
          dispatch({ type: "SET_UNAUTHENTICATED" });
        }
      },
      async refreshSession() {
        console.warn("SessionProvider.refreshSession not yet implemented");
      },
      resolveError() {
        dispatch({ type: "CLEAR_ERROR" });
      },
      acknowledgeLockout() {
        dispatch({ type: "CLEAR_LOCKOUT" });
      },
      setMustChangePassword(value: boolean) {
        dispatch({ type: "SET_MUST_CHANGE_PASSWORD", payload: value });
      },
    } satisfies Omit<SessionContextValue, keyof SessionState | "isAdmin" | "isAnalyst" | "isAuditor">;
  }, [dispatch]);

  const value = useMemo<SessionContextValue>(() => ({
    ...state,
    ...actions,
    isAdmin: state.user?.role === "ADMIN",
    isAnalyst: state.user?.role === "ANALYST",
    isAuditor: state.user?.role === "AUDITOR",
  }), [actions, state]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};
