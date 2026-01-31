"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { MigrationBalanceBanner } from "@/components/MigrationBalanceBanner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import Providers from "../providers";
import { getAuthState, clearAuth, fetchCsrfToken, authFetch } from "@/lib/auth";
import { Loader2, X, Keyboard } from "lucide-react";

/**
 * Keyboard shortcuts configuration
 */
const KEYBOARD_SHORTCUTS = [
    { key: "?", description: "Show keyboard shortcuts help" },
    { key: "g d", description: "Go to Dashboard" },
    { key: "g u", description: "Go to Upload" },
    { key: "g m", description: "Go to Migrations" },
    { key: "g r", description: "Go to Reports" },
    { key: "g s", description: "Go to Settings" },
    { key: "Esc", description: "Close dialogs and modals" },
];

/**
 * Keyboard Shortcuts Help Modal
 * Shows all available keyboard shortcuts when user presses "?"
 */
function KeyboardShortcutsModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
    if (!isOpen) return null;

    return (
        <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={onClose}
            role="dialog"
            aria-modal="true"
            aria-labelledby="keyboard-shortcuts-title"
        >
            <div
                className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-xl"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Keyboard className="w-5 h-5 text-[var(--bridge-blue)]" aria-hidden="true" />
                        <h3 id="keyboard-shortcuts-title" className="text-lg font-semibold text-gray-900">
                            Keyboard Shortcuts
                        </h3>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-gray-100 rounded transition-colors"
                        aria-label="Close keyboard shortcuts help"
                    >
                        <X className="w-5 h-5 text-gray-500" aria-hidden="true" />
                    </button>
                </div>

                <div className="space-y-2">
                    {KEYBOARD_SHORTCUTS.map((shortcut) => (
                        <div
                            key={shortcut.key}
                            className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
                        >
                            <span className="text-sm text-gray-600">{shortcut.description}</span>
                            <kbd className="px-2 py-1 bg-gray-100 text-gray-700 text-xs font-mono rounded border border-gray-200">
                                {shortcut.key}
                            </kbd>
                        </div>
                    ))}
                </div>

                <p className="mt-4 text-xs text-gray-400 text-center">
                    Press <kbd className="px-1 bg-gray-100 rounded">?</kbd> anytime to see this help
                </p>
            </div>
        </div>
    );
}

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

/**
 * Dashboard Error Fallback Component
 * Shown when the dashboard encounters an unrecoverable error
 */
function DashboardErrorFallback() {
    return (
        <div className="flex h-screen items-center justify-center bg-gray-50">
            <div className="text-center max-w-md mx-auto p-8">
                <div className="w-16 h-16 mx-auto mb-6 bg-red-100 rounded-full flex items-center justify-center">
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-8 w-8 text-red-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        />
                    </svg>
                </div>
                <h2 className="text-xl font-semibold text-gray-900 mb-2">
                    Something went wrong
                </h2>
                <p className="text-gray-600 mb-6">
                    We encountered an unexpected error. Please try refreshing the page
                    or contact support if the problem persists.
                </p>
                <div className="flex gap-3 justify-center">
                    <button
                        onClick={() => window.location.reload()}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                        Refresh Page
                    </button>
                    <button
                        onClick={() => window.location.href = '/'}
                        className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition-colors"
                    >
                        Go to Dashboard
                    </button>
                </div>
            </div>
        </div>
    );
}

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
    const [showShortcutsHelp, setShowShortcutsHelp] = useState(false);
    const [pendingKey, setPendingKey] = useState<string | null>(null);

    // Keyboard shortcut handler
    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        // Don't trigger shortcuts when typing in inputs
        const target = e.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
            return;
        }

        // Close modal on Escape
        if (e.key === 'Escape') {
            setShowShortcutsHelp(false);
            setPendingKey(null);
            return;
        }

        // Show help on ?
        if (e.key === '?' || (e.shiftKey && e.key === '/')) {
            e.preventDefault();
            setShowShortcutsHelp(true);
            return;
        }

        // Handle two-key shortcuts (g + letter)
        if (pendingKey === 'g') {
            setPendingKey(null);
            switch (e.key.toLowerCase()) {
                case 'd':
                    router.push('/');
                    break;
                case 'u':
                    router.push('/upload');
                    break;
                case 'm':
                    router.push('/migrations');
                    break;
                case 'r':
                    router.push('/reports');
                    break;
                case 's':
                    router.push('/settings');
                    break;
            }
            return;
        }

        // Start two-key sequence
        if (e.key === 'g') {
            setPendingKey('g');
            // Clear pending key after 1 second if no follow-up
            setTimeout(() => setPendingKey(null), 1000);
        }
    }, [pendingKey, router]);

    // Set up keyboard shortcut listener
    useEffect(() => {
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [handleKeyDown]);

    useEffect(() => {
        // Check authentication on mount
        const checkAuth = async () => {
            const authState = getAuthState();

            if (!authState.isAuthenticated) {
                // Not logged in - redirect to login immediately
                router.replace("/login");
                return;
            }

            // SECURITY: Fetch CSRF token for subsequent requests
            await fetchCsrfToken();

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

    // Check system health status with timeout
    const checkSystemHealth = async () => {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        try {
            const response = await fetch(`${API_URL}/health`, {
                method: 'GET',
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'healthy') {
                    setSystemStatus("operational");
                } else {
                    setSystemStatus("degraded");
                }
            } else {
                setSystemStatus("down");
            }
        } catch {
            clearTimeout(timeoutId);
            setSystemStatus("down");
        }
    };

    // Logout handler - calls backend and clears local storage
    const handleLogout = async () => {
        try {
            // SECURITY: Use authFetch for proper CSRF token handling
            await authFetch(`${API_URL}/api/auth/logout`, {
                method: 'POST',
            });
        } catch {
            // Continue with local logout even if backend call fails
            if (process.env.NODE_ENV === 'development') {
                console.error("Backend logout failed");
            }
        }

        // Clear local auth state
        clearAuth();
        router.push("/login");
    };

    // Return loading UI without duplicate html/body tags
    if (isLoading) {
        return (
            <div className="flex h-screen items-center justify-center bg-gray-50">
                <div className="text-center">
                    <Loader2 className="w-8 h-8 mx-auto animate-spin text-blue-600 mb-4" />
                    <p className="text-gray-500">Checking authentication...</p>
                </div>
            </div>
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
        <Providers>
            {/* SECURITY FIX: Wrap entire dashboard with ErrorBoundary */}
            <ErrorBoundary fallback={<DashboardErrorFallback />}>
                <div className="flex h-screen overflow-hidden">
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
                                    onClick={() => setShowShortcutsHelp(true)}
                                    className="text-xs text-gray-500 hover:text-gray-700 transition-colors flex items-center gap-1"
                                    aria-label="Show keyboard shortcuts (press ? key)"
                                    title="Keyboard shortcuts (?)"
                                >
                                    <Keyboard className="w-3 h-3" aria-hidden="true" />
                                    <span className="sr-only">Keyboard shortcuts</span>
                                </button>
                                <button
                                    onClick={handleLogout}
                                    className="text-xs text-gray-500 hover:text-red-600 transition-colors"
                                    aria-label="Log out of your account"
                                >
                                    Logout
                                </button>
                            </div>
                        </header>

                        {/* Page Content - wrapped in its own ErrorBoundary */}
                        <main className="flex-1 overflow-auto bg-gray-50 p-6" role="main">
                            <MigrationBalanceBanner />
                            <ErrorBoundary>
                                {children}
                            </ErrorBoundary>
                        </main>
                    </div>
                </div>

                {/* Keyboard Shortcuts Help Modal */}
                <KeyboardShortcutsModal
                    isOpen={showShortcutsHelp}
                    onClose={() => setShowShortcutsHelp(false)}
                />
            </ErrorBoundary>
        </Providers>
    );
}
