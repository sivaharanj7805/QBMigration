/**
 * Migration Hooks for ForensicBridge
 *
 * React Query hooks for fetching, creating, and managing migrations.
 * Includes automatic cache invalidation and optimistic updates.
 *
 * @module hooks/useMigrations
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Hook for fetching all migrations.
 *
 * Returns a paginated list of all migrations for the current user/tenant.
 * Automatically refetches on window focus and has a short cache time
 * to ensure data freshness.
 *
 * @returns {UseQueryResult} React Query result object containing:
 *   - data: Array of migration objects with status, progress, etc.
 *   - isLoading: Boolean indicating if the request is in progress
 *   - error: Error object if the request failed
 *   - refetch: Function to manually trigger a refetch
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useMigrations();
 * return <MigrationsTable migrations={data?.migrations || []} />;
 * ```
 */
export function useMigrations() {
    return useQuery({
        queryKey: ["migrations"],
        // FIX F-06: Accept signal from React Query for proper abort on unmount
        queryFn: async ({ signal }) => {
            const result = await api.getMigrations(undefined, undefined, signal);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        staleTime: 10000, // Cache for 10 seconds
    });
}

/**
 * Hook for fetching bulk status of multiple migrations.
 *
 * Efficiently fetches status updates for multiple migrations in a single request.
 * Used on the migrations list page to show real-time progress updates.
 *
 * @param {string[]} migrationIds - Optional array of migration IDs to fetch status for.
 *   If not provided, fetches status for all recent migrations.
 *
 * @returns {UseQueryResult} React Query result object containing:
 *   - data: Object mapping migration IDs to their current status
 *   - isLoading: Boolean indicating if the request is in progress
 *   - error: Error object if the request failed
 *
 * @example
 * ```tsx
 * const ids = migrations.map(m => m.migration_id);
 * const { data: statuses } = useBulkStatus(ids);
 * ```
 */
export function useBulkStatus(migrationIds?: string[]) {
    return useQuery({
        queryKey: ["bulk-status", migrationIds],
        // FIX: Accept signal parameter from React Query for proper abort handling on unmount
        queryFn: async ({ signal }) => {
            const result = await api.getBulkStatus(migrationIds, signal);
            if (!result.success) throw new Error(result.error);
            return result.data;
        },
        refetchInterval: 5000, // Refresh every 5 seconds
        staleTime: 3000,
    });
}

/**
 * Hook for starting a migration.
 *
 * Initiates the migration process for a previously uploaded QuickBooks file.
 * Requires QBO credentials to be provided for the destination connection.
 * Automatically invalidates related queries on success.
 *
 * @returns {UseMutationResult} React Query mutation object containing:
 *   - mutate: Function to trigger the mutation
 *   - mutateAsync: Async version that returns a Promise
 *   - isLoading: Boolean indicating if the mutation is in progress
 *   - error: Error object if the mutation failed
 *
 * @example
 * ```tsx
 * const startMigration = useStartMigration();
 * await startMigration.mutateAsync({
 *   migrationId: 'abc123',
 *   qboCredentials: { client_id, client_secret, refresh_token }
 * });
 * ```
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
 * Hook for cancelling an in-progress migration.
 *
 * Safely cancels a running migration and cleans up any partial data.
 * Only works for migrations in 'processing' or 'in_progress' status.
 * Automatically invalidates related queries on success.
 *
 * @returns {UseMutationResult} React Query mutation object containing:
 *   - mutate: Function to trigger the cancellation
 *   - mutateAsync: Async version that returns a Promise
 *   - isLoading: Boolean indicating if the cancellation is in progress
 *   - error: Error object if the cancellation failed
 *
 * @example
 * ```tsx
 * const cancelMigration = useCancelMigration();
 * await cancelMigration.mutateAsync(migrationId);
 * ```
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
 * Hook for retrying a failed migration.
 *
 * Restarts a migration that previously failed. The migration will
 * resume from the beginning with fresh state.
 * Automatically invalidates related queries on success.
 *
 * @returns {UseMutationResult} React Query mutation object containing:
 *   - mutate: Function to trigger the retry
 *   - mutateAsync: Async version that returns a Promise
 *   - isLoading: Boolean indicating if the retry is in progress
 *   - error: Error object if the retry failed
 *
 * @example
 * ```tsx
 * const retryMigration = useRetryMigration();
 * await retryMigration.mutateAsync(migrationId);
 * ```
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
