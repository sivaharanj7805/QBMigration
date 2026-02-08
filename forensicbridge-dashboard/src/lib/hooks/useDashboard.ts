/**
 * Dashboard Hooks for ForensicBridge
 *
 * React Query hooks for fetching and caching dashboard data.
 * All hooks implement proper caching and automatic refetching.
 *
 * @module hooks/useDashboard
 */

import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Hook for fetching dashboard overview statistics.
 *
 * Provides aggregate statistics about migrations, success rates,
 * and system health for display on the main dashboard.
 *
 * @returns {UseQueryResult} React Query result object containing:
 *   - data: Overview statistics (totalMigrations, successRate, etc.)
 *   - isLoading: Boolean indicating if the request is in progress
 *   - error: Error object if the request failed
 *   - refetch: Function to manually trigger a refetch
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useDashboardOverview();
 * if (isLoading) return <Spinner />;
 * if (error) return <ErrorMessage error={error} />;
 * return <StatsCard stats={data} />;
 * ```
 */
export function useDashboardOverview() {
    return useQuery({
        queryKey: ["dashboard-overview"],
        // FIX F-06: Accept signal from React Query for proper abort on unmount
        queryFn: async ({ signal }) => {
            const result = await api.getDashboardOverview(signal);
            if (!result.success) throw new Error(result.error);
            return result.data?.overview;
        },
        staleTime: 30000, // Cache for 30 seconds
        refetchInterval: 60000, // Refresh every minute
    });
}

/**
 * Hook for fetching recent activity feed.
 *
 * Returns a list of recent migration activities including uploads,
 * completions, errors, and verifications.
 *
 * @returns {UseQueryResult} React Query result object containing:
 *   - data: Array of activity objects with timestamp, type, and message
 *   - isLoading: Boolean indicating if the request is in progress
 *   - error: Error object if the request failed
 *
 * @example
 * ```tsx
 * const { data: activities, isLoading } = useRecentActivity();
 * return <ForensicFeed events={activities} isLive={true} />;
 * ```
 */
export function useRecentActivity() {
    return useQuery({
        queryKey: ["recent-activity"],
        // FIX F-06: Accept signal from React Query for proper abort on unmount
        queryFn: async ({ signal }) => {
            const result = await api.getRecentActivity(signal);
            if (!result.success) throw new Error(result.error);
            return result.data?.activities || [];
        },
        staleTime: 10000, // Cache for 10 seconds
        refetchInterval: 15000, // Refresh every 15 seconds
    });
}

/**
 * Hook for checking API health status.
 *
 * Performs a lightweight health check against the backend API.
 * Used to display system status indicator in the dashboard header.
 *
 * @returns {UseQueryResult} React Query result object containing:
 *   - data: Health status object with status, timestamp, and checks
 *   - isLoading: Boolean indicating if the request is in progress
 *   - error: Error object if the request failed
 *
 * @example
 * ```tsx
 * const { data: health } = useHealth();
 * const status = health?.status === 'healthy' ? 'operational' : 'degraded';
 * ```
 */
export function useHealth() {
    return useQuery({
        queryKey: ["health"],
        // FIX F-06: Accept signal from React Query for proper abort on unmount
        queryFn: async ({ signal }) => {
            const result = await api.getHealth(signal);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
}
