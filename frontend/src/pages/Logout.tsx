import { useEffect } from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { useSession } from "../contexts/sessionContext";
import interceptLogo from "../assets/Intercept-White.svg?url";

export default function Logout() {
    const navigate = useViewTransitionNavigate();
    const { logout, status } = useSession();

    useEffect(() => {
        const performLogout = async () => {
            await logout();
            // Redirect to login page after logout
            navigate("/login");
        };

        performLogout();
    }, [logout, navigate]);

    return (
        <div className="flex h-screen w-full items-center justify-center bg-default-background">
            <div className="flex flex-col items-center gap-6">
                <img 
                    src={interceptLogo} 
                    alt="Intercept Logo" 
                    className="h-12 w-auto"
                />
                <div className="text-default-font">
                    {status === "unauthenticated" ? "Logged out successfully..." : "Logging out..."}
                </div>
            </div>
        </div>
    );
}