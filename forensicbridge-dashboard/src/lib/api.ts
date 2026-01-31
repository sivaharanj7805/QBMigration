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

// HIGH-09 FIX: Default retry configuration
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 1000;

class ApiClient {
    private baseUrl: string;
    private token: string | null = null;
    private timeout: number;
    private maxRetries: number;
    private retryDelayMs: number;

    constructor(
        baseUrl: string,
        timeout: number = DEFAULT_TIMEOUT_MS,
        maxRetries: number = DEFAULT_MAX_RETRIES,
        retryDelayMs: number = DEFAULT_RETRY_DELAY_MS
    ) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.maxRetries = maxRetries;
        this.retryDelayMs = retryDelayMs;
    }

    /**
     * HIGH-09 FIX: Exponential backoff delay
     */
    private async delay(attempt: number): Promise<void> {
        const delayMs = this.retryDelayMs * Math.pow(2, attempt);
        return new Promise(resolve => setTimeout(resolve, delayMs));
    }

    /**
     * HIGH-09 FIX: Check if error is retryable
     */
    private isRetryableError(status: number, error?: Error): boolean {
        // Retry on network errors
        if (error && (error.name === 'TypeError' || error.message.includes('Network'))) {
            return true;
        }
        // Retry on 5xx server errors and 429 rate limiting
        return status >= 500 || status === 429;
    }

    setToken(token: string | null) {
        this.token = token;
    }

    clearToken() {
        this.token = null;
    }

    /**
     * Get the current token, falling back to localStorage if not set
     */
    private getToken(): string | null {
        if (this.token) return this.token;
        if (typeof window !== 'undefined') {
            return localStorage.getItem('token');
        }
        return null;
    }

    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
        schema?: z.ZodSchema<T>
    ): Promise<ApiResponse<T>> {
        const url = `${this.baseUrl}${endpoint}`;
        const token = this.getToken();

        const headers: HeadersInit = {
            "Content-Type": "application/json",
            ...(token && { Authorization: `Bearer ${token}` }),
            ...options.headers,
        };

        // HIGH-09 FIX: Retry loop with exponential backoff
        let lastError: Error | null = null;
        let lastStatus = 0;

        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
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
                lastStatus = response.status;

                // SECURITY FIX: Parse and validate JSON with schema
                const rawData = await response.json();

                if (!response.ok) {
                    // HIGH-09 FIX: Check if error is retryable
                    if (this.isRetryableError(response.status) && attempt < this.maxRetries) {
                        console.warn(`[API] Retryable error ${response.status} on ${endpoint}, attempt ${attempt + 1}/${this.maxRetries + 1}`);
                        await this.delay(attempt);
                        continue;
                    }

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
                lastError = error instanceof Error ? error : new Error(String(error));

                // FIX FE-04: Specific error message for timeout
                if (lastError.name === 'AbortError') {
                    // Don't retry timeouts
                    return {
                        success: false,
                        error: `Request timed out after ${this.timeout / 1000} seconds`,
                    };
                }

                // HIGH-09 FIX: Retry on network errors
                if (this.isRetryableError(0, lastError) && attempt < this.maxRetries) {
                    console.warn(`[API] Network error on ${endpoint}, attempt ${attempt + 1}/${this.maxRetries + 1}: ${lastError.message}`);
                    await this.delay(attempt);
                    continue;
                }

                return {
                    success: false,
                    error: lastError.message || "Network error",
                };
            }
        }

        // Should not reach here, but handle gracefully
        return {
            success: false,
            error: lastError?.message || `Request failed after ${this.maxRetries + 1} attempts`,
        };
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

    async getMigrationStats() {
        return this.request<{
            stats: {
                migrations_this_month: number;
                total_records: string;
                avg_duration: string;
                success_rate: string;
            };
        }>("/api/migrations/stats");
    }

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
        const token = this.getToken();

        try {
            const response = await fetch(url, {
                credentials: "include",
                headers: token ? { Authorization: `Bearer ${token}` } : {},
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
        }>("/health");
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
        const token = this.getToken();

        try {
            const response = await fetch(url, {
                credentials: "include",
                headers: token ? { Authorization: `Bearer ${token}` } : {},
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
