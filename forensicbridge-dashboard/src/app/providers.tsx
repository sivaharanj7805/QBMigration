"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * MED-01 to MED-15 FIX: App providers with Error Boundary wrapper
 */
export default function Providers({ children }: { children: React.ReactNode }) {
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 1000,
                retry: false, // Don't retry on failure during debugging
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
