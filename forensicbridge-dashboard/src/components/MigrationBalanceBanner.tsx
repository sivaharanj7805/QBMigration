'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { AlertCircle, Package, ArrowRight, RefreshCw, Zap, Building2, Shield, Crown, Scale } from 'lucide-react';
import { authFetch } from '@/lib/auth';

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

// Auto-refresh interval in milliseconds (30 seconds)
const REFRESH_INTERVAL = 30000;

interface MigrationBalanceData {
    tier: string;
    tier_name: string;
    migrations_remaining: number;
    migrations_purchased: number;
    migrations_used: number;
    has_tier: boolean;
}

// Icons for each tier type
const TIER_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    starter: Zap,
    business: Building2,
    professional: Shield,
    enterprise: Crown,
    forensic: Scale
};

export function MigrationBalanceBanner() {
    const [balanceData, setBalanceData] = useState<MigrationBalanceData | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);

    // FIX: Track mounted state to prevent state updates on unmounted component
    const isMountedRef = useRef(true);

    const loadBalanceData = useCallback(async (showRefresh = false) => {
        try {
            if (showRefresh) setRefreshing(true);

            // SECURITY FIX: Use authFetch with httpOnly cookies instead of localStorage token
            // This prevents XSS attacks from stealing auth tokens
            // authFetch automatically includes credentials: 'include' for httpOnly cookies
            const response = await authFetch(`${API_URL}/api/auth/me`);

            // FIX: Check if mounted before setting state after async operation
            if (!isMountedRef.current) return;

            if (response.ok) {
                const data = await response.json();
                // FIX: Check if mounted again after parsing JSON
                if (!isMountedRef.current) return;

                if (data.success && data.user) {
                    setBalanceData({
                        tier: data.user.subscription_tier || 'none',
                        tier_name: data.user.tier_name || 'No Plan',
                        migrations_remaining: data.user.migrations_remaining || 0,
                        migrations_purchased: data.user.migrations_purchased || 0,
                        migrations_used: data.user.migrations_used || 0,
                        has_tier: data.user.has_tier || false,
                    });
                }
            }
        } catch (error) {
            // FIX: Only log errors in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error('Failed to load balance data:', error);
            }
        } finally {
            // FIX: Check if mounted before setting state in finally block
            if (isMountedRef.current) {
                setLoading(false);
                setRefreshing(false);
            }
        }
    }, []);

    // Initial load and cleanup
    useEffect(() => {
        // FIX: Reset mounted state on mount
        isMountedRef.current = true;
        loadBalanceData();

        // FIX: Mark as unmounted on cleanup to prevent state updates
        return () => {
            isMountedRef.current = false;
        };
    }, [loadBalanceData]);

    // Auto-refresh every 30 seconds
    useEffect(() => {
        const interval = setInterval(() => {
            loadBalanceData(true);
        }, REFRESH_INTERVAL);

        return () => clearInterval(interval);
    }, [loadBalanceData]);

    if (loading) {
        return null; // Don't show banner while loading
    }

    // Show prompt to select a plan if user has no tier
    if (!balanceData?.has_tier) {
        return (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mb-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <AlertCircle className="w-5 h-5 text-amber-500" />
                        <div>
                            <p className="font-medium text-amber-700 dark:text-amber-300">
                                No plan selected yet
                            </p>
                            <p className="text-sm text-amber-600 dark:text-amber-400">
                                Select a migration plan to start migrating your QuickBooks data
                            </p>
                        </div>
                    </div>
                    <Link
                        href="/select-tier"
                        className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                    >
                        Select Plan
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </div>
        );
    }

    const TierIcon = TIER_ICONS[balanceData.tier] || Zap;

    return (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 mb-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Package className="w-5 h-5 text-emerald-500" />
                    <div>
                        <div className="flex items-center gap-2">
                            <p className="font-medium text-gray-900 dark:text-white">
                                {balanceData.tier_name} Plan
                            </p>
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/50 rounded-full text-xs font-bold text-emerald-700 dark:text-emerald-300">
                                <TierIcon className="w-3 h-3" />
                                Active
                            </span>
                            {refreshing && (
                                <RefreshCw className="w-3 h-3 text-gray-400 animate-spin" />
                            )}
                        </div>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            {balanceData.migrations_remaining} migration{balanceData.migrations_remaining !== 1 ? 's' : ''} remaining
                            {' '}&middot; {balanceData.migrations_used} used
                        </p>
                    </div>
                </div>
                <Link
                    href="/select-tier?upgrade=true"
                    className="flex items-center gap-2 px-4 py-2 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-white rounded-lg hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors text-sm"
                >
                    Change Plan
                </Link>
            </div>
        </div>
    );
}
