import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

// FIX: Add max refetch count to prevent infinite polling
const MAX_REFETCH_COUNT = 3600; // Stop after 1 hour (3600 refetches at 1 second each)
const REFETCH_INTERVAL_MS = 1000;

export function useLiveStatus(migrationId: string) {
    return useQuery({
        queryKey: ["liveStatus", migrationId],
        queryFn: async () => {
            // Real Backend Call
            const response = await api.getLiveStatus(migrationId);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch live status");
            }
            return response.data;
        },
        refetchInterval: (query) => {
            const status = query.state.data?.status;
            // Stop polling if migration is completed or failed
            if (status === "completed" || status === "failed") {
                return false;
            }
            // FIX: Stop polling after max refetch count to prevent infinite loops
            const refetchCount = query.state.dataUpdateCount;
            if (refetchCount >= MAX_REFETCH_COUNT) {
                console.warn(`[useLiveStatus] Stopped polling after ${MAX_REFETCH_COUNT} refetches`);
                return false;
            }
            return REFETCH_INTERVAL_MS;
        },
        enabled: !!migrationId,
        // FIX: Add retry configuration for failed requests
        retry: 3,
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
    });
}

export function useTrialBalance(migrationId: string, isCompleted: boolean) {
    return useQuery({
        queryKey: ["trialBalance", migrationId],
        queryFn: async () => {
            // Real Backend Call
            const response = await api.getTrialBalance(migrationId);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch trial balance");
            }
            return response.data;
        },
        enabled: !!migrationId && isCompleted,
    });
}

export function useAuditCertificate(migrationId: string, isCompleted: boolean) {
    return useQuery({
        queryKey: ["auditCertificate", migrationId],
        queryFn: async () => {
            // Real Backend Call
            const response = await api.getAuditCertificatePreview(migrationId);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch certificate preview");
            }
            return response.data;
        },
        enabled: !!migrationId && isCompleted,
    });
}
