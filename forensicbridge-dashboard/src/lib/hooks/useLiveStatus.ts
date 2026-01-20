import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

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
            return status === "completed" || status === "failed" ? false : 1000;
        },
        enabled: !!migrationId,
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
