import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Hook for fetching all migrations
 */
export function useMigrations() {
    return useQuery({
        queryKey: ["migrations"],
        queryFn: async () => {
            const result = await api.getMigrations();
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        staleTime: 10000, // Cache for 10 seconds
    });
}

/**
 * Hook for fetching bulk status of multiple migrations
 */
export function useBulkStatus(migrationIds?: string[]) {
    return useQuery({
        queryKey: ["bulk-status", migrationIds],
        queryFn: async () => {
            const result = await api.getBulkStatus(migrationIds);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        refetchInterval: 5000, // Refresh every 5 seconds
        staleTime: 3000,
    });
}

/**
 * Hook for starting a migration
 */
export function useStartMigration() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async ({
            migrationId,
            qboCredentials,
        }: {
            migrationId: string;
            qboCredentials: {
                client_id: string;
                client_secret: string;
                refresh_token: string;
            };
        }) => {
            const result = await api.startMigration(migrationId, qboCredentials);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["migrations"] });
            queryClient.invalidateQueries({ queryKey: ["bulk-status"] });
        },
    });
}

/**
 * Hook for cancelling a migration
 */
export function useCancelMigration() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (migrationId: string) => {
            const result = await api.cancelMigration(migrationId);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["migrations"] });
            queryClient.invalidateQueries({ queryKey: ["bulk-status"] });
        },
    });
}

/**
 * Hook for retrying a migration
 */
export function useRetryMigration() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: async (migrationId: string) => {
            const result = await api.retryMigration(migrationId);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["migrations"] });
            queryClient.invalidateQueries({ queryKey: ["bulk-status"] });
        },
    });
}
