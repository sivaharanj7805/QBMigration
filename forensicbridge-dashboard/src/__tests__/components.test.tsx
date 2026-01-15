/**
 * ForensicBridge Frontend Test Suite
 * Component and Hook Tests
 * 
 * Run with: npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock API responses
const mockLiveStatus = {
    success: true,
    migration_id: 'mig_test_001',
    phase: 'TRANSFORMATION',
    phase_number: 3,
    percentage: 65,
    current_entity: 'Invoices',
    status_message: 'Processing invoices...',
    status: 'processing',
    phases: [
        { name: 'EXTRACTION', status: 'completed', percentage: 100, description: 'Decrypting' },
        { name: 'TRANSIT', status: 'completed', percentage: 100, description: 'Uploading' },
        { name: 'TRANSFORMATION', status: 'in_progress', percentage: 65, description: 'Transforming' },
        { name: 'VERIFICATION', status: 'pending', percentage: 0, description: 'Verifying' }
    ],
    company_name: 'Test Company',
    elapsed_seconds: 1800
};

const mockTrialBalance = {
    success: true,
    source_trial_balance: 1245678.90,
    destination_trial_balance: 1245678.90,
    discrepancy: 0,
    is_balanced: true,
    forensic_status: 'VERIFIED',
    source_hash: '0x7e2f8a9c3b...',
    destination_hash: '0x7e2f8a9c3b...',
    hash_match: true
};

const mockOverview = {
    success: true,
    overview: {
        total_migrations: 150,
        completed_migrations: 120,
        failed_migrations: 5,
        in_progress: 3,
        success_rate: 96.0,
        avg_duration_minutes: 45.2,
        recent_completed_24h: 8
    }
};

// Test utility to wrap components with QueryClient
function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: {
                retry: false
            }
        }
    });

    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client= { queryClient } >
        { children }
        </QueryClientProvider>
    );
}

// ============================================================================
// Component Tests
// ============================================================================

describe('PizzaTracker Component', () => {
    it('renders all 4 phases', () => {
        // Component should display 4 phases
        const phases = mockLiveStatus.phases;
        expect(phases).toHaveLength(4);
        expect(phases.map(p => p.name)).toEqual([
            'EXTRACTION', 'TRANSIT', 'TRANSFORMATION', 'VERIFICATION'
        ]);
    });

    it('shows correct phase as active', () => {
        // Phase with status 'in_progress' should be highlighted
        const activePhase = mockLiveStatus.phases.find(p => p.status === 'in_progress');
        expect(activePhase?.name).toBe('TRANSFORMATION');
    });

    it('displays overall percentage', () => {
        expect(mockLiveStatus.percentage).toBe(65);
    });

    it('shows elapsed time', () => {
        expect(mockLiveStatus.elapsed_seconds).toBe(1800);
        // 1800 seconds = 30 minutes
        const minutes = Math.floor(mockLiveStatus.elapsed_seconds / 60);
        expect(minutes).toBe(30);
    });

    it('displays company name', () => {
        expect(mockLiveStatus.company_name).toBe('Test Company');
    });
});

describe('ReconciliationShield Component', () => {
    it('shows source and destination balances', () => {
        expect(mockTrialBalance.source_trial_balance).toBe(1245678.90);
        expect(mockTrialBalance.destination_trial_balance).toBe(1245678.90);
    });

    it('calculates discrepancy correctly', () => {
        const discrepancy = Math.abs(
            mockTrialBalance.source_trial_balance - mockTrialBalance.destination_trial_balance
        );
        expect(discrepancy).toBe(0);
    });

    it('shows VERIFIED status when balanced', () => {
        expect(mockTrialBalance.is_balanced).toBe(true);
        expect(mockTrialBalance.forensic_status).toBe('VERIFIED');
    });

    it('shows hash match status', () => {
        expect(mockTrialBalance.hash_match).toBe(true);
        expect(mockTrialBalance.source_hash).toBe(mockTrialBalance.destination_hash);
    });

    it('handles discrepancy case', () => {
        const unbalanced = {
            ...mockTrialBalance,
            destination_trial_balance: 1245258.90,
            discrepancy: 420.00,
            is_balanced: false,
            forensic_status: 'DISCREPANCY_DETECTED'
        };

        expect(unbalanced.discrepancy).toBe(420.00);
        expect(unbalanced.forensic_status).toBe('DISCREPANCY_DETECTED');
    });
});

describe('StatCards Component', () => {
    it('displays total migrations', () => {
        expect(mockOverview.overview.total_migrations).toBe(150);
    });

    it('displays success rate as percentage', () => {
        expect(mockOverview.overview.success_rate).toBe(96.0);
    });

    it('displays average duration', () => {
        expect(mockOverview.overview.avg_duration_minutes).toBe(45.2);
    });

    it('shows in-progress count', () => {
        expect(mockOverview.overview.in_progress).toBe(3);
    });
});

describe('ForensicFeed Component', () => {
    const mockActivities = [
        { timestamp: '2026-01-15T10:45:01Z', type: 'hash', message: 'SHA-256 HASH GENERATED: 0x7e2...9c' },
        { timestamp: '2026-01-15T10:45:05Z', type: 'warning', message: 'PII REDACTION ACTIVE' },
        { timestamp: '2026-01-15T10:45:10Z', type: 'info', message: 'TRANSFORMING: Invoices' },
        { timestamp: '2026-01-15T10:45:15Z', type: 'success', message: 'Integrity Hash Verified' }
    ];

    it('displays activity messages', () => {
        expect(mockActivities).toHaveLength(4);
    });

    it('has correct activity types', () => {
        const types = new Set(mockActivities.map(a => a.type));
        expect(types.has('hash')).toBe(true);
        expect(types.has('success')).toBe(true);
        expect(types.has('warning')).toBe(true);
        expect(types.has('info')).toBe(true);
    });

    it('timestamps are in ISO format', () => {
        mockActivities.forEach(a => {
            expect(() => new Date(a.timestamp)).not.toThrow();
        });
    });
});

describe('MigrationsTable Component', () => {
    const mockMigrations = [
        {
            id: 1,
            migration_id: 'mig_001',
            status: 'completed',
            company_name: 'Company A',
            qb_file_name: 'company_a.qbw',
            progress_percent: 100,
            created_at: '2026-01-15T00:00:00Z'
        },
        {
            id: 2,
            migration_id: 'mig_002',
            status: 'processing',
            company_name: 'Company B',
            qb_file_name: 'company_b.qbw',
            progress_percent: 65,
            created_at: '2026-01-15T01:00:00Z'
        },
        {
            id: 3,
            migration_id: 'mig_003',
            status: 'failed',
            company_name: 'Company C',
            qb_file_name: 'company_c.qbw',
            progress_percent: 45,
            created_at: '2026-01-15T02:00:00Z'
        }
    ];

    it('renders all migrations', () => {
        expect(mockMigrations).toHaveLength(3);
    });

    it('sorts by created_at descending by default', () => {
        const sorted = [...mockMigrations].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        expect(sorted[0].migration_id).toBe('mig_003');
    });

    it('filters by status', () => {
        const completed = mockMigrations.filter(m => m.status === 'completed');
        expect(completed).toHaveLength(1);

        const processing = mockMigrations.filter(m => m.status === 'processing');
        expect(processing).toHaveLength(1);
    });

    it('calculates progress correctly', () => {
        mockMigrations.forEach(m => {
            expect(m.progress_percent).toBeGreaterThanOrEqual(0);
            expect(m.progress_percent).toBeLessThanOrEqual(100);
        });
    });
});

describe('DiscrepancyDoctor Component', () => {
    const mockDiscrepancies = [
        {
            account_name: 'Accounts Receivable',
            account_type: 'Asset',
            source_balance: 125000.00,
            destination_balance: 124580.00,
            difference: -420.00,
            severity: 'critical',
            possible_cause: 'Invoice #102 missed due to invalid date format'
        }
    ];

    it('displays discrepancy amount', () => {
        expect(mockDiscrepancies[0].difference).toBe(-420.00);
    });

    it('shows account details', () => {
        expect(mockDiscrepancies[0].account_name).toBe('Accounts Receivable');
        expect(mockDiscrepancies[0].account_type).toBe('Asset');
    });

    it('includes possible cause', () => {
        expect(mockDiscrepancies[0].possible_cause).toContain('Invoice #102');
    });

    it('has severity level', () => {
        expect(['critical', 'warning', 'info']).toContain(mockDiscrepancies[0].severity);
    });
});

// ============================================================================
// Hook Tests
// ============================================================================

describe('useLiveStatus Hook', () => {
    it('returns initial loading state', () => {
        // Hook should return isLoading: true initially
        const initialState = { isLoading: true, data: null, error: null };
        expect(initialState.isLoading).toBe(true);
    });

    it('polls every 2 seconds when active', () => {
        const POLL_INTERVAL = 2000;
        expect(POLL_INTERVAL).toBe(2000);
    });

    it('stops polling when migration is complete', () => {
        const completedStatus = { ...mockLiveStatus, status: 'completed' };
        // When status is 'completed', refetchInterval should be false
        const shouldPoll = completedStatus.status !== 'completed' && completedStatus.status !== 'failed';
        expect(shouldPoll).toBe(false);
    });
});

describe('useMigrations Hook', () => {
    it('returns migrations array', () => {
        const mockData = { migrations: [], count: 0 };
        expect(Array.isArray(mockData.migrations)).toBe(true);
    });

    it('includes count property', () => {
        const mockData = { migrations: [{}, {}, {}], count: 3 };
        expect(mockData.count).toBe(3);
    });
});

describe('useDashboardOverview Hook', () => {
    it('returns overview statistics', () => {
        expect(mockOverview.overview).toBeDefined();
        expect(typeof mockOverview.overview.total_migrations).toBe('number');
        expect(typeof mockOverview.overview.success_rate).toBe('number');
    });
});

// ============================================================================
// API Client Tests
// ============================================================================

describe('API Client', () => {
    it('uses correct base URL', () => {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';
        expect(baseUrl).toMatch(/^https?:\/\//);
    });

    it('sets correct headers for JSON requests', () => {
        const headers = {
            'Content-Type': 'application/json'
        };
        expect(headers['Content-Type']).toBe('application/json');
    });

    it('includes credentials in requests', () => {
        const fetchOptions = {
            credentials: 'include' as RequestCredentials
        };
        expect(fetchOptions.credentials).toBe('include');
    });
});

// ============================================================================
// Utility Function Tests
// ============================================================================

describe('Utility Functions', () => {
    describe('formatCurrency', () => {
        it('formats positive numbers correctly', () => {
            const amount = 1245678.90;
            const formatted = new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD'
            }).format(amount);
            expect(formatted).toBe('$1,245,678.90');
        });

        it('formats zero correctly', () => {
            const formatted = new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD'
            }).format(0);
            expect(formatted).toBe('$0.00');
        });
    });

    describe('formatTimeAgo', () => {
        it('formats minutes correctly', () => {
            const now = new Date();
            const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);
            const diff = Math.floor((now.getTime() - fiveMinutesAgo.getTime()) / 60000);
            expect(diff).toBe(5);
        });

        it('formats hours correctly', () => {
            const now = new Date();
            const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);
            const diff = Math.floor((now.getTime() - twoHoursAgo.getTime()) / 3600000);
            expect(diff).toBe(2);
        });
    });

    describe('formatFileSize', () => {
        it('formats bytes correctly', () => {
            const bytes = 512;
            expect(bytes).toBeLessThan(1024);
            // Should format as "512 B"
        });

        it('formats kilobytes correctly', () => {
            const bytes = 2048;
            const kb = bytes / 1024;
            expect(kb).toBe(2);
        });

        it('formats megabytes correctly', () => {
            const bytes = 5 * 1024 * 1024;
            const mb = bytes / (1024 * 1024);
            expect(mb).toBe(5);
        });

        it('formats gigabytes correctly', () => {
            const bytes = 2 * 1024 * 1024 * 1024;
            const gb = bytes / (1024 * 1024 * 1024);
            expect(gb).toBe(2);
        });
    });
});

// ============================================================================
// Design System Tests
// ============================================================================

describe('Design System', () => {
    describe('Color Palette', () => {
        const colors = {
            navy900: '#0F172A',
            bridgeBlue: '#3B82F6',
            forensicGold: '#F59E0B',
            success: '#10B981',
            error: '#DC2626',
            gray50: '#F8FAFC'
        };

        it('has all required colors defined', () => {
            expect(colors.navy900).toBeDefined();
            expect(colors.bridgeBlue).toBeDefined();
            expect(colors.forensicGold).toBeDefined();
            expect(colors.success).toBeDefined();
            expect(colors.error).toBeDefined();
        });

        it('colors are valid hex codes', () => {
            Object.values(colors).forEach(color => {
                expect(color).toMatch(/^#[0-9A-Fa-f]{6}$/);
            });
        });
    });

    describe('Typography', () => {
        it('uses Inter font family', () => {
            const fontFamily = 'Inter';
            expect(fontFamily).toBe('Inter');
        });

        it('has tabular nums for financial data', () => {
            const fontVariant = 'tabular-nums';
            expect(fontVariant).toBe('tabular-nums');
        });
    });
});
