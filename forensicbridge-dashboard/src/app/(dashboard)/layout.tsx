"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { MigrationBalanceBanner } from "@/components/MigrationBalanceBanner";
import Providers from "../providers";
import { getAuthState, clearAuth } from "@/lib/auth";
import { Loader2 } from "lucide-react";

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const router = useRouter();
    const [isLoading, setIsLoading] = useState(true);
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [systemStatus, setSystemStatus] = useState<"operational" | "degraded" | "down">("operational");
    const [userName, setUserName] = useState("");

    useEffect(() => {
        // Check authentication on mount
        const checkAuth = () => {
            const authState = getAuthState();

            if (!authState.isAuthenticated) {
                // Not logged in - redirect to login immediately
                router.replace("/login");
                return; // Don't set loading to false, let redirect happen
            }

            // User is authenticated
            setIsAuthenticated(true);
            setIsLoading(false);

            // Get user name for display
            if (authState.user) {
                const name = authState.user.name ||
                    authState.user.first_name ||
                    authState.user.email?.split('@')[0] ||
                    "User";
                setUserName(name);
            }
        };

        checkAuth();
        checkSystemHealth();
    }, [router]);

    // Check system health status
    const checkSystemHealth = async () => {
        try {
            const response = await fetch(`${API_URL}/health`, {
                method: 'GET',
                redirect: 'manual', // Prevent ERR_TOO_MANY_REDIRECTS from redirect loops
            });
            // redirect: 'manual' returns opaque redirect responses (type === 'opaqueredirect')
            // which have status 0 — treat as server being down
            if (response.type === 'opaqueredirect' || !response.ok) {
                setSystemStatus("down");
                return;
            }
            const data = await response.json();
            if (data.status === 'healthy') {
                setSystemStatus("operational");
            } else {
                setSystemStatus("degraded");
            }
        } catch (error) {
            setSystemStatus("down");
        }
    };

    // Logout handler - calls backend and clears local storage
    const handleLogout = async () => {
        try {
            // Call backend logout to clear server session
            await fetch(`${API_URL}/api/auth/logout`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
                }
            });
        } catch (error) {
            // Continue with local logout even if backend call fails
            console.error("Backend logout failed:", error);
        }

        // Clear local auth state
        clearAuth();
        router.push("/login");
    };

    // Show loading while checking auth
    if (isLoading) {
        return (
            <html lang="en">
                <body className="flex h-screen items-center justify-center bg-gray-50">
                    <div className="text-center">
                        <Loader2 className="w-8 h-8 mx-auto animate-spin text-blue-600 mb-4" />
                        <p className="text-gray-500">Checking authentication...</p>
                    </div>
                </body>
            </html>
        );
    }

    // Not authenticated - don't render anything (will redirect)
    if (!isAuthenticated) {
        return null;
    }

    // Get status display
    const statusConfig = {
        operational: { text: "All Systems Operational", color: "bg-green-100 text-green-700", icon: "✓" },
        degraded: { text: "Degraded Performance", color: "bg-yellow-100 text-yellow-700", icon: "⚠" },
        down: { text: "System Issues", color: "bg-red-100 text-red-700", icon: "✗" }
    };
    const status = statusConfig[systemStatus];

    return (
        <html lang="en">
            <body className="flex h-screen overflow-hidden">
                <Providers>
                    {/* Sidebar */}
                    <Sidebar />

                    {/* Main Content */}
                    <div className="flex-1 flex flex-col overflow-hidden">
                        {/* Header */}
                        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
                            <div className="flex items-center gap-4">
                                <h2 className="text-sm text-gray-500">
                                    Welcome back, <span className="font-medium text-gray-900">{userName}</span>
                                </h2>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className={`text-xs ${status.color} px-2 py-1 rounded-full`}>
                                    {status.icon} {status.text}
                                </span>
                                <button
                                    onClick={handleLogout}
                                    className="text-xs text-gray-500 hover:text-red-600 transition-colors"
                                >
                                    Logout
                                </button>
                            </div>
                        </header>

                        {/* Page Content */}
                        <main className="flex-1 overflow-auto bg-gray-50 p-6">
                            <MigrationBalanceBanner />
                            {children}
                        </main>
                    </div>
                </Providers>
            </body>
        </html>
    );
}

