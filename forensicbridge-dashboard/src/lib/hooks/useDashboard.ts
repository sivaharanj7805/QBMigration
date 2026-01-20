import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Hook for fetching dashboard overview statistics
 */
export function useDashboardOverview() {
    return useQuery({
        queryKey: ["dashboard-overview"],
        queryFn: async () => {
            const result = await api.getDashboardOverview();
            if (!result.success) throw new Error(result.error);
            return result.data?.overview;
        },
        staleTime: 30000, // Cache for 30 seconds
        refetchInterval: 60000, // Refresh every minute
    });
}

/**
 * Hook for fetching recent activity feed
 */
export function useRecentActivity() {
    return useQuery({
        queryKey: ["recent-activity"],
        queryFn: async () => {
            const result = await api.getRecentActivity();
            if (!result.success) throw new Error(result.error);
            return result.data?.activities || [];
        },
        staleTime: 10000, // Cache for 10 seconds
        refetchInterval: 15000, // Refresh every 15 seconds
    });
}

/**
 * Hook for health check
 */
export function useHealth() {
    return useQuery({
        queryKey: ["health"],
        queryFn: async () => {
            const result = await api.getHealth();
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        staleTime: 30000,
        refetchInterval: 60000,
    });
}
