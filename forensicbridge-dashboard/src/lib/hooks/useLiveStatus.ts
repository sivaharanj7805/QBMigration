/**
 * Live Status Hooks for ForensicBridge Dashboard
 *
 * Provides real-time migration status polling with:
 * - Terminal status detection (stops polling when completed/failed)
 * - Exponential backoff on errors
 * - Request cancellation via AbortController
 * - Maximum polling duration protection
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useEffect } from "react";
import { api } from "@/lib/api";

// Constants
const INITIAL_POLL_INTERVAL = 1000; // 1 second
const MAX_POLL_INTERVAL = 30000; // 30 seconds (max backoff)
const MAX_POLL_DURATION = 3600000; // 1 hour max polling
const TERMINAL_STATUSES = ["completed", "failed", "cancelled", "error"];

/**
 * Check if a status is terminal (migration is done)
 */
function isTerminalStatus(status: string | undefined): boolean {
    if (!status) return false;
    return TERMINAL_STATUSES.includes(status.toLowerCase());
}

/**
 * Live Status Hook with Terminal Detection
 *
 * Polls for migration status and automatically stops when:
 * - Migration reaches a terminal status (completed, failed, cancelled)
 * - Maximum polling duration is exceeded
 * - Component unmounts
 */
export function useLiveStatus(migrationId: string) {
    const queryClient = useQueryClient();
    const pollStartTime = useRef<number>(0);
    const errorCountRef = useRef<number>(0);

    // Reset poll start time when migration ID changes
    useEffect(() => {
        pollStartTime.current = Date.now();
        errorCountRef.current = 0;
    }, [migrationId]);

    return useQuery({
        queryKey: ["liveStatus", migrationId],
        queryFn: async ({ signal }) => {
            const response = await api.getLiveStatus(migrationId, signal);
            if (!response.success || !response.data) {
                // Track consecutive errors for backoff
                errorCountRef.current++;
                throw new Error(response.error || "Failed to fetch live status");
            }

            // Reset error count on success
            errorCountRef.current = 0;
            return response.data;
        },
        refetchInterval: (query) => {
            const status = query.state.data?.status;

            // STOP POLLING: Terminal status reached
            if (isTerminalStatus(status)) {
                return false;
            }

            // STOP POLLING: Max duration exceeded
            const elapsedMs = Date.now() - pollStartTime.current;
            if (elapsedMs >= MAX_POLL_DURATION) {
                if (process.env.NODE_ENV === 'development') {
                    console.warn(`[useLiveStatus] Stopped polling - max duration exceeded`);
                }
                return false;
            }

            // Calculate interval with exponential backoff on errors
            if (errorCountRef.current > 0) {
                const backoffInterval = Math.min(
                    INITIAL_POLL_INTERVAL * Math.pow(2, errorCountRef.current),
                    MAX_POLL_INTERVAL
                );
                return backoffInterval;
            }

            return INITIAL_POLL_INTERVAL;
        },
        enabled: !!migrationId,
        retry: 3,
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10000),
        staleTime: 500, // Consider data stale after 500ms
    });
}

/**
 * Trial Balance Hook
 *
 * Fetches trial balance data when migration is completed.
 * Only enabled after migration reaches completed status.
 */
export function useTrialBalance(migrationId: string, isCompleted: boolean) {
    return useQuery({
        queryKey: ["trialBalance", migrationId],
        queryFn: async ({ signal }) => {
            const response = await api.getTrialBalance(migrationId, signal);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch trial balance");
            }
            return response.data;
        },
        enabled: !!migrationId && isCompleted,
        staleTime: 60000, // Cache for 1 minute (trial balance doesn't change)
    });
}

/**
 * Audit Certificate Hook
 *
 * Fetches certificate preview when migration is completed.
 */
export function useAuditCertificate(migrationId: string, isCompleted: boolean) {
    return useQuery({
        queryKey: ["auditCertificate", migrationId],
        queryFn: async ({ signal }) => {
            const response = await api.getAuditCertificatePreview(migrationId, signal);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch certificate preview");
            }
            return response.data;
        },
        enabled: !!migrationId && isCompleted,
        staleTime: 60000, // Cache for 1 minute
    });
}

/**
 * Bulk Status Hook
 *
 * Fetches status for multiple migrations at once.
 * Used on the migrations list page for efficient polling.
 */
export function useBulkStatus(
    migrationIds: string[],
    options: {
        enabled?: boolean;
        pollInterval?: number;
    } = {}
) {
    const { enabled = true, pollInterval = 5000 } = options;
    const hasActiveMigrations = useRef(false);

    return useQuery({
        queryKey: ["bulkStatus", migrationIds],
        queryFn: async ({ signal }) => {
            const response = await api.getBulkStatus(migrationIds, signal);
            if (!response.success || !response.data) {
                throw new Error(response.error || "Failed to fetch bulk status");
            }

            // Check if any migrations are still active
            const migrations = Object.values(response.data.migrations);
            hasActiveMigrations.current = migrations.some(
                (m) => !isTerminalStatus(m.status)
            );

            return response.data;
        },
        refetchInterval: (query) => {
            // Only poll if there are active migrations
            if (!hasActiveMigrations.current) {
                return false;
            }
            return pollInterval;
        },
        enabled: enabled && migrationIds.length > 0,
        staleTime: 2000,
    });
}
