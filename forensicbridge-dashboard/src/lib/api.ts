/**
 * ForensicBridge API Client
 * 
 * Handles all communication with the QBMigrationServer backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface ApiResponse<T> {
    success: boolean;
    data?: T;
    error?: string;
}

class ApiClient {
    private baseUrl: string;
    private token: string | null = null;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    setToken(token: string) {
        this.token = token;
    }

    private async request<T>(
        endpoint: string,
        options: RequestInit = {}
    ): Promise<ApiResponse<T>> {
        const url = `${this.baseUrl}${endpoint}`;

        const headers: HeadersInit = {
            "Content-Type": "application/json",
            ...(this.token && { Authorization: `Bearer ${this.token}` }),
            ...options.headers,
        };

        try {
            const response = await fetch(url, {
                ...options,
                headers,
                credentials: "include",
            });

            const data = await response.json();

            if (!response.ok) {
                return {
                    success: false,
                    error: data.error || `HTTP ${response.status}`,
                };
            }

            return {
                success: true,
                data,
            };
        } catch (error) {
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
        return this.request<{
            overview: {
                total_migrations: number;
                completed_migrations: number;
                failed_migrations: number;
                in_progress: number;
                success_rate: number;
                avg_duration_minutes: number;
                recent_completed_24h: number;
            };
        }>("/api/dashboard/overview");
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
        }>("/health");
    }
}

// Export singleton instance
export const api = new ApiClient(API_BASE_URL);

// Export class for testing
export { ApiClient };
