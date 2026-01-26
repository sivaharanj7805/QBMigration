/**
 * ForensicBridge API Client
 *
 * Handles all communication with the QBMigrationServer backend.
 * Uses Zod for runtime schema validation to prevent XSS and type errors.
 */

import { z } from 'zod';
import {
    DashboardOverviewSchema,
    MigrationListSchema,
    MigrationStatusSchema,
    TrialBalanceSchema,
    LoginResponseSchema,
    UserInfoSchema,
    UploadSessionSchema,
    UploadCompleteSchema,
} from './schemas';

// FIX FE-01: Production-safe API URL configuration
// In production, NEXT_PUBLIC_API_URL must be set - fallback only for development
const API_BASE_URL = (() => {
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl) return envUrl;

    // Only allow localhost fallback in development
    if (process.env.NODE_ENV === 'development') {
        console.warn('[API] NEXT_PUBLIC_API_URL not set - using localhost (development only)');
        return "http://localhost:5000";
    }

    // In production without env var, throw clear error
    throw new Error(
        'NEXT_PUBLIC_API_URL environment variable is required in production. ' +
        'Set it to your API server URL.'
    );
})();

interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

// FIX FE-04: Default request timeout (30 seconds)
const DEFAULT_TIMEOUT_MS = 30000;

class ApiClient {
    private baseUrl: string;
    private token: string | null = null;
    private timeout: number;

    constructor(baseUrl: string, timeout: number = DEFAULT_TIMEOUT_MS) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    setToken(token: string) {
        this.token = token;
    }

    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
        schema?: z.ZodSchema<T>
    ): Promise<ApiResponse<T>> {
        const url = `${this.baseUrl}${endpoint}`;

        const headers: HeadersInit = {
            "Content-Type": "application/json",
            ...(this.token && { Authorization: `Bearer ${this.token}` }),
            ...options.headers,
        };

        // FIX FE-04: Add request timeout using AbortController
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(url, {
                ...options,
                headers,
                credentials: "include",
                signal: controller.signal,
            });
            clearTimeout(timeoutId);

            // Handle opaque redirect responses (from redirect: 'manual')
            if (response.type === 'opaqueredirect') {
                return {
                    success: false,
                    error: 'Server returned a redirect. The API endpoint may be misconfigured.',
                };
            }

            // SECURITY FIX: Parse and validate JSON with schema
            const rawData = await response.json();

            if (!response.ok) {
                return {
                    success: false,
                    error: rawData.error || `HTTP ${response.status}`,
                };
            }

            // SECURITY: Validate response data with Zod schema if provided
            if (schema) {
                try {
                    const validatedData = schema.parse(rawData);
                    return {
                        success: true,
                        data: validatedData,
                    };
                } catch (validationError) {
                    console.error('Schema validation failed:', validationError);
                    return {
                        success: false,
                        error: 'Invalid API response format. This may indicate a security issue.',
                    };
                }
            }

            // Fallback: return unvalidated data (backwards compatibility)
            return {
                success: true,
                data: rawData as T,
            };
        } catch (error) {
            clearTimeout(timeoutId);

            // FIX FE-04: Specific error message for timeout
            if (error instanceof Error && error.name === 'AbortError') {
                return {
                    success: false,
                    error: `Request timed out after ${this.timeout / 1000} seconds`,
                };
            }

            return {
                success: false,
                error: error instanceof Error ? error.message : "Network error",
            };
        }
    }

    // ==========================================
    // Dashboard Endpoints
    // ==========================================

    async getDashboardOverview() {
        return this.request(
            "/api/dashboard/overview",
            {},
            DashboardOverviewSchema
        );
    }

    async getRecentActivity() {
        return this.request<{
            activities: Array<{
                timestamp: string;
                type: string;
                message: string;
                migration_id: string;
                icon: string;
            }>;
        }>("/api/dashboard/recent-activity");
    }

    // ==========================================
    // Migration Endpoints
    // ==========================================

    async getMigrations() {
        return this.request<{
            migrations: Array<{
                id: number;
                migration_id: string;
                status: string;
                company_name: string;
                qb_file_name: string;
                progress_percent: number;
                created_at: string;
                completed_at: string | null;
                s3_uri: string;
            }>;
            count: number;
        }>("/api/migrations");
    }

    async getMigration(migrationId: string) {
        return this.request<{
            migration: {
                id: number;
                migration_id: string;
                status: string;
                company_name: string;
                progress_percent: number;
                created_at: string;
                completed_at: string | null;
                [key: string]: unknown;
            };
        }>(`/api/migrations/${migrationId}`);
    }

    async getLiveStatus(migrationId: string) {
        return this.request<{
            migration_id: string;
            phase: string;
            phase_number: number;
            percentage: number;
            current_entity: string | null;
            status_message: string;
            status: string;
            alerts: string[];
            integrity_verified: boolean;
            phases: Array<{
                name: string;
                status: "pending" | "in_progress" | "completed";
                percentage: number;
                description: string;
            }>;
            company_name: string;
            started_at: string;
            elapsed_seconds: number;
            completed_at?: string;
            duration_seconds?: number;
            error?: string;
        }>(`/api/migrations/${migrationId}/live-status`);
    }

    async getBulkStatus(migrationIds?: string[]) {
        return this.request<{
            migrations: Record<string, {
                id: number;
                migration_id: string;
                status: string;
                progress_percent: number;
                company_name: string;
                qb_file_name: string;
                file_size: number | null;
                created_at: string;
                completed_at: string | null;
                current_step: string | null;
            }>;
            count: number;
        }>("/api/migrations/bulk-status", {
            method: "POST",
            body: JSON.stringify({ migration_ids: migrationIds || [] }),
        });
    }

    async getMigrationStatus(migrationId: string) {
        return this.request<{
            migration_id: string;
            status: string;
            progress_percent: number;
            created_at: string;
            current_step?: string;
            completed_at?: string;
        }>(`/api/migrations/${migrationId}/status`);
    }

    async startMigration(migrationId: string, qboCredentials: {
        client_id: string;
        client_secret: string;
        refresh_token: string;
    }) {
        return this.request<{
            migration_id: string;
            instance_id: string;
            status: string;
            message: string;
        }>(`/api/migrations/${migrationId}/start`, {
            method: "POST",
            body: JSON.stringify({ qbo_credentials: qboCredentials }),
        });
    }

    async cancelMigration(migrationId: string) {
        return this.request<{ message: string }>(`/api/migrations/${migrationId}/cancel`, {
            method: "POST",
        });
    }

    async retryMigration(migrationId: string) {
        return this.request<{
            message: string;
            migration_id: string;
        }>(`/api/migrations/${migrationId}/retry`, {
            method: "POST",
        });
    }

    // ==========================================
    // Verification Endpoints
    // ==========================================

    async getTrialBalance(migrationId: string) {
        return this.request<{
            source_trial_balance: number | null;
            destination_trial_balance: number | null;
            discrepancy: number | null;
            is_balanced: boolean | null;
            forensic_status: string;
            verification_timestamp: string | null;
            source_hash?: string;
            destination_hash?: string;
            hash_match?: boolean;
        }>(`/api/migrations/${migrationId}/trial-balance`);
    }

    async downloadAuditCertificate(migrationId: string): Promise<Blob | null> {
        const url = `${this.baseUrl}/api/migrations/${migrationId}/audit-certificate`;

        try {
            const response = await fetch(url, {
                credentials: "include",
                headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
            });

            if (!response.ok) {
                console.error("Failed to download certificate");
                return null;
            }

            return await response.blob();
        } catch (error) {
            console.error("Download error:", error);
            return null;
        }
    }

    async getAuditCertificatePreview(migrationId: string) {
        return this.request<{
            available: boolean;
            migration_id: string;
            company_name: string;
            completed_at: string | null;
            download_url: string;
        }>(`/api/migrations/${migrationId}/audit-certificate/preview`);
    }

    // ==========================================
    // Health Check
    // ==========================================

    async getHealth() {
        return this.request<{
            status: string;
            timestamp: string;
            checks: Record<string, string>;
        }>("/health", { redirect: 'manual' });
    }

    // ==========================================
    // Caseware Export Mode
    // ==========================================

    async exportCasewareBundle(migrationId: string) {
        return this.request<{
            success: boolean;
            message: string;
            bundle_id: string;
            files: string[];
            stats?: Record<string, number>;
            download_url: string;
        }>(`/api/migrations/${migrationId}/export-caseware`, {
            method: "POST",
        });
    }

    async downloadCasewareBundle(migrationId: string): Promise<Blob> {
        const url = `${this.baseUrl}/api/migrations/${migrationId}/caseware-bundle`;

        try {
            const response = await fetch(url, {
                credentials: "include",
                headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
            });

            if (!response.ok) {
                // Try to extract error from response
                let errorMsg = `HTTP ${response.status}: Download failed`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.error || errorMsg;
                } catch {
                    // Not JSON, use default
                }
                throw new Error(errorMsg);
            }

            return await response.blob();
        } catch (error) {
            console.error("Download error:", error);
            throw error;
        }
    }

    async getCasewareStatus(migrationId: string) {
        return this.request<{
            migration_id: string;
            destination: "qbo" | "caseware";
            caseware_bundle_ready: boolean;
            download_url: string | null;
            can_generate: boolean;
        }>(`/api/migrations/${migrationId}/caseware-status`);
    }
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL);

// Export class for testing
export { ApiClient };
