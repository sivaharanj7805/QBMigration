/**
 * Zod Schemas for Runtime API Response Validation
 *
 * Provides type-safe runtime validation of API responses to prevent:
 * - XSS attacks from malformed data
 * - Type errors from unexpected API changes
 * - Dashboard crashes from missing fields
 */

import { z } from 'zod';

// ==========================================
// Base Schemas
// ==========================================

export const ApiErrorSchema = z.object({
    success: z.literal(false),
    error: z.string(),
    error_code: z.string().optional(),
});

export const ApiSuccessSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
    z.object({
        success: z.literal(true),
        data: dataSchema.optional(),
    });

// ==========================================
// Dashboard Schemas
// ==========================================

export const DashboardOverviewSchema = z.object({
    overview: z.object({
        total_migrations: z.number().int().nonnegative(),
        completed_migrations: z.number().int().nonnegative(),
        failed_migrations: z.number().int().nonnegative(),
        in_progress: z.number().int().nonnegative(),
        success_rate: z.number().min(0).max(100),
        avg_duration_minutes: z.number().nonnegative(),
        recent_completed_24h: z.number().int().nonnegative(),
        pending_review: z.number().int().nonnegative().optional(),
    }),
});

export const MigrationStatusSchema = z.object({
    id: z.number().int().optional(),
    migration_id: z.string(),
    status: z.enum(['pending', 'uploading', 'uploaded', 'provisioning', 'processing', 'completed', 'failed', 'cancelled']),
    progress_percent: z.number().min(0).max(100),
    current_step: z.string().optional().nullable(),
    company_name: z.string().optional().nullable(),
    qb_file_name: z.string().optional().nullable(),
    created_at: z.string(),
    completed_at: z.string().optional().nullable(),
    error_message: z.string().optional().nullable(),
    s3_uri: z.string().optional().nullable(),
    customers_migrated: z.number().int().nonnegative().optional(),
    vendors_migrated: z.number().int().nonnegative().optional(),
    invoices_migrated: z.number().int().nonnegative().optional(),
    bills_migrated: z.number().int().nonnegative().optional(),
});

export const MigrationListSchema = z.object({
    migrations: z.array(MigrationStatusSchema),
    pagination: z.object({
        page: z.number().int().positive(),
        per_page: z.number().int().positive(),
        total_items: z.number().int().nonnegative(),
        total_pages: z.number().int().nonnegative(),
        has_next: z.boolean().optional(),
        has_prev: z.boolean().optional(),
    }),
    count: z.number().int().nonnegative().optional(),
});

export const TrialBalanceSchema = z.object({
    source_trial_balance: z.number().optional().nullable(),
    destination_trial_balance: z.number().optional().nullable(),
    discrepancy: z.number().optional().nullable(),
    is_balanced: z.boolean().optional().nullable(),
    forensic_status: z.enum(['VERIFIED', 'DISCREPANCY_DETECTED', 'PENDING', 'NOT_AVAILABLE']),
    verification_timestamp: z.string().optional().nullable(),
    total_debits: z.number().optional(),
    total_credits: z.number().optional(),
});

// ==========================================
// Auth Schemas
// ==========================================

// FIX F-03: Include csrf_token in login response schema
export const LoginResponseSchema = z.object({
    success: z.boolean(),
    token: z.string(),
    csrf_token: z.string().optional(),
    user: z.object({
        id: z.number().int().positive(),
        email: z.string().email(),
        first_name: z.string(),
        last_name: z.string(),
        company_name: z.string().optional(),
    }),
});

export const UserInfoSchema = z.object({
    id: z.number().int().positive(),
    email: z.string().email(),
    first_name: z.string(),
    last_name: z.string(),
    company_name: z.string().optional(),
    tier: z.string(),
    tier_name: z.string(),
    migrations_remaining: z.number().int().nonnegative(),
    migrations_purchased: z.number().int().nonnegative(),
    migrations_used: z.number().int().nonnegative(),
});

// ==========================================
// Upload Schemas
// ==========================================

export const UploadSessionSchema = z.object({
    session_id: z.string(),
    upload_url: z.string().url().optional(),
    expires_at: z.string().optional(),
});

export const UploadCompleteSchema = z.object({
    success: z.boolean(),
    migration_id: z.string(),
    message: z.string().optional(),
});

// ==========================================
// Type Exports
// ==========================================

export type DashboardOverview = z.infer<typeof DashboardOverviewSchema>;
export type MigrationStatus = z.infer<typeof MigrationStatusSchema>;
export type MigrationList = z.infer<typeof MigrationListSchema>;
export type TrialBalance = z.infer<typeof TrialBalanceSchema>;
export type LoginResponse = z.infer<typeof LoginResponseSchema>;
export type UserInfo = z.infer<typeof UserInfoSchema>;
export type UploadSession = z.infer<typeof UploadSessionSchema>;
export type UploadComplete = z.infer<typeof UploadCompleteSchema>;
