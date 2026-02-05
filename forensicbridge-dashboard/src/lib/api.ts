/**
 * ForensicBridge API Client
 *
 * Handles all communication with the QBMigrationServer backend.
 * Uses Zod for runtime schema validation to prevent XSS and type errors.
 *
 * SECURITY FEATURES:
 * - Uses httpOnly cookies via credentials: 'include'
 * - Includes CSRF token in all mutation requests
 * - AbortController with timeouts for all requests
 * - Retry with exponential backoff for transient failures
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
import { getCsrfToken, setCsrfToken } from './auth';

// FIX: Production-safe API URL configuration
// Moved error throwing to runtime (when API is first used) instead of module load time
// This prevents build/SSR failures and allows for better error handling
const getApiBaseUrl = (): string => {
    const envUrl = process.env.NEXT_PUBLIC_API_URL;
    if (envUrl) return envUrl;

    if (process.env.NODE_ENV === 'development') {
        console.warn('[API] NEXT_PUBLIC_API_URL not set - using localhost (development only)');
        return "http://localhost:5000";
    }

    // In production, return empty string - actual error will be thrown at runtime
    return "";
};

// Lazy initialization - URL is resolved when first accessed
let _apiBaseUrl: string | null = null;
const API_BASE_URL = (): string => {
    if (_apiBaseUrl === null) {
        _apiBaseUrl = getApiBaseUrl();
    }

    // FIX: Throw error at runtime when API is actually used, not at module load time
    if (!_apiBaseUrl && process.env.NODE_ENV === 'production') {
        throw new Error(
            'NEXT_PUBLIC_API_URL environment variable is required in production. ' +
            'Set it to your API server URL.'
        );
    }

    return _apiBaseUrl;
};

interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

// Timeout constants
const DEFAULT_TIMEOUT_MS = 30000; // 30 seconds
const DOWNLOAD_TIMEOUT_MS = 300000; // 5 minutes for file downloads

// Retry configuration
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 1000;

class ApiClient {
    private baseUrl: string;
    private timeout: number;
    private maxRetries: number;
    private retryDelayMs: number;

    // AUDIT FIX HIGH-10: Request deduplication to prevent rapid duplicate API calls
    private inflightRequests: Map<string, Promise<ApiResponse<unknown>>> = new Map();
    // Minimum interval between identical requests (milliseconds)
    private requestThrottleMs: number;

    constructor(
        baseUrl: string,
        timeout: number = DEFAULT_TIMEOUT_MS,
        maxRetries: number = DEFAULT_MAX_RETRIES,
        retryDelayMs: number = DEFAULT_RETRY_DELAY_MS,
        requestThrottleMs: number = 200
    ) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.maxRetries = maxRetries;
        this.retryDelayMs = retryDelayMs;
        this.requestThrottleMs = requestThrottleMs;
    }

    /**
     * Exponential backoff delay
     */
    private async delay(attempt: number): Promise<void> {
        const delayMs = this.retryDelayMs * Math.pow(2, attempt);
        return new Promise(resolve => setTimeout(resolve, delayMs));
    }

    /**
     * Check if error is retryable
     */
    private isRetryableError(status: number, error?: Error): boolean {
        if (error && (error.name === 'TypeError' || error.message.includes('Network'))) {
            return true;
        }
        return status >= 500 || status === 429;
    }

    /**
     * Generate a unique request ID for correlation
     */
    private generateRequestId(): string {
        return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
    }

    /**
     * AUDIT FIX HIGH-10: Deduplicate identical GET requests that are in-flight
     * Prevents rapid simultaneous API calls to the same endpoint
     */
    private async deduplicatedRequest<T>(
        endpoint: string,
        options: RequestInit = {},
        schema?: z.ZodSchema<T>,
        customTimeout?: number,
        signal?: AbortSignal
    ): Promise<ApiResponse<T>> {
        const method = (options.method || 'GET').toUpperCase();

        // Only deduplicate GET requests (mutations should always execute)
        if (method !== 'GET') {
            return this.request<T>(endpoint, options, schema, customTimeout, signal);
        }

        const dedupeKey = `${method}:${endpoint}`;
        const existing = this.inflightRequests.get(dedupeKey);
        if (existing) {
            return existing as Promise<ApiResponse<T>>;
        }

        const requestPromise = this.request<T>(endpoint, options, schema, customTimeout, signal);

        this.inflightRequests.set(dedupeKey, requestPromise as Promise<ApiResponse<unknown>>);

        try {
            const result = await requestPromise;
            return result;
        } finally {
            // Remove after a short throttle window to prevent rapid re-requests
            setTimeout(() => {
                this.inflightRequests.delete(dedupeKey);
            }, this.requestThrottleMs);
        }
    }

    /**
     * Core request method with CSRF, timeout, and retry support
     */
    private async request<T>(
        endpoint: string,
        options: RequestInit = {},
        schema?: z.ZodSchema<T>,
        customTimeout?: number,
        signal?: AbortSignal
    ): Promise<ApiResponse<T>> {
        const url = `${this.baseUrl}${endpoint}`;
        const requestId = this.generateRequestId();
        const method = (options.method || 'GET').toUpperCase();

        const headers: HeadersInit = {
            "Content-Type": "application/json",
            "X-Request-ID": requestId,
            ...options.headers,
        };

        // SECURITY: Add CSRF token for mutation requests
        const csrfToken = getCsrfToken();
        if (method !== 'GET' && method !== 'HEAD' && csrfToken) {
            (headers as Record<string, string>)['X-CSRF-Token'] = csrfToken;
        }

        let lastError: Error | null = null;
        let lastStatus = 0;

        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
            // Create AbortController for timeout
            const controller = new AbortController();
            const timeoutMs = customTimeout || this.timeout;
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

            // Support external abort signal
            const onAbort = () => controller.abort();
            if (signal) {
                if (signal.aborted) {
                    clearTimeout(timeoutId);
                    return { success: false, error: 'Request cancelled' };
                }
                signal.addEventListener('abort', onAbort);
            }

            try {
                const response = await fetch(url, {
                    ...options,
                    headers,
                    credentials: "include", // SECURITY: Send httpOnly cookies
                    signal: controller.signal,
                });
                clearTimeout(timeoutId);
                if (signal) {
                    signal.removeEventListener('abort', onAbort);
                }
                lastStatus = response.status;

                // Extract CSRF token from response header if provided
                const newCsrfToken = response.headers.get('X-CSRF-Token');
                if (newCsrfToken) {
                    setCsrfToken(newCsrfToken);
                }

                let rawData;
                try {
                    rawData = await response.json();
                } catch {
                    rawData = { error: `HTTP ${response.status}: ${response.statusText}` };
                }

                if (!response.ok) {
                    if (this.isRetryableError(response.status) && attempt < this.maxRetries) {
                        if (process.env.NODE_ENV === 'development') {
                            console.warn(`[API] Retryable error ${response.status} on ${endpoint}, attempt ${attempt + 1}/${this.maxRetries + 1}`);
                        }
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
                        return { success: true, data: validatedData };
                    } catch (validationError) {
                        if (process.env.NODE_ENV === 'development') {
                            console.error('Schema validation failed:', validationError);
                        }
                        return {
                            success: false,
                            error: 'Invalid API response format. This may indicate a security issue.',
                        };
                    }
                }

                return { success: true, data: rawData as T };
            } catch (error) {
                clearTimeout(timeoutId);
                if (signal) {
                    signal.removeEventListener('abort', onAbort);
                }
                lastError = error instanceof Error ? error : new Error(String(error));

                if (lastError.name === 'AbortError') {
                    return {
                        success: false,
                        error: `Request timed out after ${(customTimeout || this.timeout) / 1000} seconds`,
                    };
                }

                if (this.isRetryableError(0, lastError) && attempt < this.maxRetries) {
                    if (process.env.NODE_ENV === 'development') {
                        console.warn(`[API] Network error on ${endpoint}, attempt ${attempt + 1}/${this.maxRetries + 1}: ${lastError.message}`);
                    }
                    await this.delay(attempt);
                    continue;
                }

                return {
                    success: false,
                    error: lastError.message || "Network error",
                };
            }
        }

        return {
            success: false,
            error: lastError?.message || `Request failed after ${this.maxRetries + 1} attempts`,
        };
    }

    /**
     * Download a file with timeout and abort support
     * SECURITY FIX: Added timeout to prevent hung downloads
     */
    private async downloadFile(
        endpoint: string,
        signal?: AbortSignal,
        timeout: number = DOWNLOAD_TIMEOUT_MS
    ): Promise<Blob | null> {
        const url = `${this.baseUrl}${endpoint}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        // Support external abort signal
        const onAbort = () => controller.abort();
        if (signal) {
            if (signal.aborted) {
                clearTimeout(timeoutId);
                return null;
            }
            signal.addEventListener('abort', onAbort);
        }

        const csrfToken = getCsrfToken();
        const headers: HeadersInit = {};
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }

        try {
            const response = await fetch(url, {
                credentials: "include",
                headers,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }

            if (!response.ok) {
                if (process.env.NODE_ENV === 'development') {
                    console.error(`Download failed: HTTP ${response.status}`);
                }
                return null;
            }

            return await response.blob();
        } catch (error) {
            clearTimeout(timeoutId);
            if (signal) {
                signal.removeEventListener('abort', onAbort);
            }

            if (error instanceof Error && error.name === 'AbortError') {
                if (process.env.NODE_ENV === 'development') {
                    console.error(`Download timed out after ${timeout / 1000} seconds`);
                }
            } else if (process.env.NODE_ENV === 'development') {
                console.error("Download error:", error);
            }

            return null;
        }
    }

    // ==========================================
    // Dashboard Endpoints
    // ==========================================

    async getDashboardOverview(signal?: AbortSignal) {
        return this.deduplicatedRequest(
            "/api/dashboard/overview",
            {},
            DashboardOverviewSchema,
            undefined,
            signal
        );
    }

    async getRecentActivity(signal?: AbortSignal) {
        return this.deduplicatedRequest<{
            activities: Array<{
                timestamp: string;
                type: string;
                message: string;
                migration_id: string;
                icon: string;
            }>;
        }>("/api/dashboard/recent-activity", {}, undefined, undefined, signal);
    }

    // ==========================================
    // Migration Endpoints
    // ==========================================

    async getMigrationStats(signal?: AbortSignal) {
        return this.deduplicatedRequest<{
            stats: {
                migrations_this_month: number;
                total_records: string;
                avg_duration: string;
                success_rate: string;
            };
        }>("/api/migrations/stats", {}, undefined, undefined, signal);
    }

    async getMigrations(page: number = 1, perPage: number = 20, signal?: AbortSignal) {
        return this.deduplicatedRequest<{
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
            page: number;
            per_page: number;
            total_pages: number;
        }>(`/api/migrations?page=${page}&per_page=${perPage}`, {}, undefined, undefined, signal);
    }

    async getMigration(migrationId: string, signal?: AbortSignal) {
        return this.deduplicatedRequest<{
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
        }>(`/api/migrations/${migrationId}`, {}, undefined, undefined, signal);
    }

    async getLiveStatus(migrationId: string, signal?: AbortSignal) {
        return this.deduplicatedRequest<{
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
        }>(`/api/migrations/${migrationId}/live-status`, {}, undefined, undefined, signal);
    }

    async getBulkStatus(migrationIds?: string[], signal?: AbortSignal) {
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
        }, undefined, undefined, signal);
    }

    async getMigrationStatus(migrationId: string, signal?: AbortSignal) {
        return this.request<{
            migration_id: string;
            status: string;
            progress_percent: number;
            created_at: string;
            current_step?: string;
            completed_at?: string;
        }>(`/api/migrations/${migrationId}/status`, {}, undefined, undefined, signal);
    }

    async startMigration(migrationId: string, qboCredentials: {
        client_id: string;
        client_secret: string;
        refresh_token: string;
    }, signal?: AbortSignal) {
        return this.request<{
            migration_id: string;
            instance_id: string;
            status: string;
            message: string;
        }>(`/api/migrations/${migrationId}/start`, {
            method: "POST",
            body: JSON.stringify({ qbo_credentials: qboCredentials }),
        }, undefined, undefined, signal);
    }

    async cancelMigration(migrationId: string, signal?: AbortSignal) {
        return this.request<{ message: string }>(`/api/migrations/${migrationId}/cancel`, {
            method: "POST",
        }, undefined, undefined, signal);
    }

    async retryMigration(migrationId: string, signal?: AbortSignal) {
        return this.request<{
            message: string;
            migration_id: string;
        }>(`/api/migrations/${migrationId}/retry`, {
            method: "POST",
        }, undefined, undefined, signal);
    }

    // ==========================================
    // Verification Endpoints
    // ==========================================

    async getTrialBalance(migrationId: string, signal?: AbortSignal) {
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
        }>(`/api/migrations/${migrationId}/trial-balance`, {}, undefined, undefined, signal);
    }

    /**
     * Download audit certificate with timeout
     * SECURITY FIX: Added timeout to prevent hung downloads
     */
    async downloadAuditCertificate(migrationId: string, signal?: AbortSignal): Promise<Blob | null> {
        return this.downloadFile(`/api/migrations/${migrationId}/audit-certificate`, signal);
    }

    async getAuditCertificatePreview(migrationId: string, signal?: AbortSignal) {
        return this.request<{
            available: boolean;
            migration_id: string;
            company_name: string;
            completed_at: string | null;
            download_url: string;
        }>(`/api/migrations/${migrationId}/audit-certificate/preview`, {}, undefined, undefined, signal);
    }

    // ==========================================
    // Health Check
    // ==========================================

    async getHealth(signal?: AbortSignal) {
        return this.request<{
            status: string;
            timestamp: string;
            checks: Record<string, string>;
        }>("/health", {}, undefined, 5000, signal);
    }

    // ==========================================
    // Caseware Export Mode
    // ==========================================

    async exportCasewareBundle(migrationId: string, signal?: AbortSignal) {
        return this.request<{
            success: boolean;
            message: string;
            bundle_id: string;
            files: string[];
            stats?: Record<string, number>;
            download_url: string;
        }>(`/api/migrations/${migrationId}/export-caseware`, {
            method: "POST",
        }, undefined, 60000, signal); // 60 second timeout for export
    }

    /**
     * Download Caseware bundle with extended timeout
     * SECURITY FIX: Added timeout to prevent hung downloads
     */
    async downloadCasewareBundle(migrationId: string, signal?: AbortSignal): Promise<Blob> {
        const blob = await this.downloadFile(
            `/api/migrations/${migrationId}/caseware-bundle`,
            signal,
            DOWNLOAD_TIMEOUT_MS
        );

        if (!blob) {
            throw new Error('Download failed or timed out');
        }

        return blob;
    }

    async getCasewareStatus(migrationId: string, signal?: AbortSignal) {
        return this.request<{
            migration_id: string;
            destination: "qbo" | "caseware";
            caseware_bundle_ready: boolean;
            download_url: string | null;
            can_generate: boolean;
        }>(`/api/migrations/${migrationId}/caseware-status`, {}, undefined, undefined, signal);
    }
}

// FIX: Lazy singleton initialization to prevent SSR/build errors
// The singleton is only created when first accessed, not at module load time
let _apiInstance: ApiClient | null = null;

function getApiInstance(): ApiClient {
    if (!_apiInstance) {
        _apiInstance = new ApiClient(API_BASE_URL());
    }
    return _apiInstance;
}

// Export api as a proxy that lazily initializes the singleton
// This prevents errors during SSR/build when env vars may not be available
export const api = new Proxy({} as ApiClient, {
    get(_target, prop: keyof ApiClient) {
        const instance = getApiInstance();
        const value = instance[prop];
        if (typeof value === 'function') {
            return value.bind(instance);
        }
        return value;
    }
});

// Export class for testing
export { ApiClient };
