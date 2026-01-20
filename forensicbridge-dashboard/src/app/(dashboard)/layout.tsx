"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
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

    useEffect(() => {
        // Check authentication on mount
        const authState = getAuthState();

        if (!authState.isAuthenticated) {
            // Not logged in - redirect to login
            router.replace("/login");
        } else {
            setIsAuthenticated(true);
            setIsLoading(false);
        }
    }, [router]);

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
    if (isLoading && !isAuthenticated) {
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
                                <h2 className="text-sm text-gray-500">Enterprise Migration Suite</h2>
                            </div>
                            <div className="flex items-center gap-4">
                                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                                    ✓ All Systems Operational
                                </span>
                                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                                    🍁 ca-central-1
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
                            {children}
                        </main>
                    </div>
                </Providers>
            </body>
        </html>
    );
}
