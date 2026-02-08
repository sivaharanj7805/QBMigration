"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * MED-01 to MED-15 FIX: App providers with Error Boundary wrapper
 */
export default function Providers({ children }: { children: React.ReactNode }) {
    // HIGH-10 FIX: Enable retries in production for transient network failures.
    // 3 retries with exponential backoff is the React Query default.
    const isProd = process.env.NODE_ENV === "production";
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 1000,
                retry: isProd ? 3 : false,
                retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
            },
        },
    }));

    return (
        <ErrorBoundary>
            <QueryClientProvider client={queryClient}>
                {children}
            </QueryClientProvider>
        </ErrorBoundary>
    );
}
