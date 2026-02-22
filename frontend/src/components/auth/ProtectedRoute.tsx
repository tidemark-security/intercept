import { ReactNode, useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useSession } from "@/contexts/sessionContext";

interface ProtectedRouteProps {
  children: ReactNode;
  requiredRole?: "ADMIN" | "ANALYST" | "AUDITOR";
}

/**
 * ProtectedRoute component that ensures users are authenticated before accessing protected pages.
 * 
 * - Redirects to /login if not authenticated
 * - Redirects to /login if mustChangePassword flag is set (user will see change password form there)
 * - Optionally checks for required role
 * - Preserves the intended destination for post-login redirect
 */
export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { status, user, mustChangePassword } = useSession();
  const location = useLocation();

  // If still checking authentication (initial load or manual login), show loading spinner
  if (status === "initializing" || status === "authenticating") {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-default-background">
        <div className="text-lg text-brand-primary">Loading...</div>
      </div>
    );
  }

  // If not authenticated, redirect to login with return URL
  if (status !== "authenticated" || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // If user must change password, redirect to login page (which will show the change password form)
  if (mustChangePassword) {
    return <Navigate to="/login" replace />;
  }

  // If role is required and user doesn't have it, redirect to home or show unauthorized
  if (requiredRole && user.role !== requiredRole) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-default-background">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-4 text-error-600">Access Denied</h1>
          <p className="text-subtext-color">
            You don't have permission to access this page.
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
