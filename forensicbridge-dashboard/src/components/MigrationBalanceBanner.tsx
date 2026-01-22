'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { AlertCircle, Package, ArrowRight, RefreshCw, Zap, Building2, Shield, Crown, Scale } from 'lucide-react';

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

// Auto-refresh interval in milliseconds (30 seconds)
const REFRESH_INTERVAL = 30000;

interface CreditsByType {
    [tierType: string]: {
        name: string;
        available: number;
        used: number;
        transaction_limit: number;
        description: string;
    };
}

interface MigrationBalanceData {
    tier: string;
    tier_name: string;
    migrations_remaining: number;
    migrations_purchased: number;
    migrations_used: number;
    has_tier: boolean;
    migration_credits?: CreditsByType;
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

    const loadBalanceData = useCallback(async (showRefresh = false) => {
        try {
            if (showRefresh) setRefreshing(true);

            const token = localStorage.getItem('token');
            if (!token) {
                setLoading(false);
                return;
            }

            const response = await fetch(`${API_URL}/api/auth/me`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success && data.user) {
                    setBalanceData({
                        tier: data.user.subscription_tier || 'none',
                        tier_name: data.user.tier_name || 'No Plan',
                        migrations_remaining: data.user.migrations_remaining || 0,
                        migrations_purchased: data.user.migrations_purchased || 0,
                        migrations_used: data.user.migrations_used || 0,
                        has_tier: data.user.has_tier || false,
                        migration_credits: data.user.migration_credits || {}
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load balance data:', error);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    // Initial load
    useEffect(() => {
        loadBalanceData();
    }, [loadBalanceData]);

    // Auto-refresh every 30 seconds
    useEffect(() => {
        const interval = setInterval(() => {
            loadBalanceData(true);
        }, REFRESH_INTERVAL);

        return () => clearInterval(interval);
    }, [loadBalanceData]);

    // Format transaction limit
    const formatLimit = (limit: number) => {
        if (limit === -1) return 'Unlimited';
        if (limit >= 1000000) return `${(limit / 1000000).toFixed(0)}M`;
        if (limit >= 1000) return `${(limit / 1000).toFixed(0)}K`;
        return limit.toString();
    };

    if (loading) {
        return null; // Don't show banner while loading
    }

    // Don't show if user has no tier yet (they'll be redirected to tier selection)
    if (!balanceData?.has_tier) {
        return (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 mb-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <AlertCircle className="w-5 h-5 text-amber-500" />
                        <div>
                            <p className="font-medium text-amber-700 dark:text-amber-300">
                                No migrations purchased yet
                            </p>
                            <p className="text-sm text-amber-600 dark:text-amber-400">
                                Purchase a migration to start migrating your QuickBooks data
                            </p>
                        </div>
                    </div>
                    <Link
                        href="/select-tier"
                        className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                    >
                        Buy Migration
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </div>
        );
    }

    // Get credits breakdown
    const credits = balanceData.migration_credits || {};
    const hasCreditsBreakdown = Object.keys(credits).length > 0;

    // Get appropriate styling based on remaining migrations
    const getBannerStyle = () => {
        if (balanceData.migrations_remaining === 0) {
            return {
                bg: 'bg-red-500/10',
                border: 'border-red-500/30',
                icon: 'text-red-500',
                badge: 'bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300'
            };
        }
        if (balanceData.migrations_remaining === 1) {
            return {
                bg: 'bg-amber-500/10',
                border: 'border-amber-500/30',
                icon: 'text-amber-500',
                badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300'
            };
        }
        return {
            bg: 'bg-emerald-500/10',
            border: 'border-emerald-500/30',
            icon: 'text-emerald-500',
            badge: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300'
        };
    };

    const style = getBannerStyle();

    return (
        <div className={`${style.bg} border ${style.border} rounded-lg p-4 mb-6`}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Package className={`w-5 h-5 ${style.icon}`} />
                    <div>
                        <div className="flex items-center gap-2">
                            <p className="font-medium text-gray-900 dark:text-white">
                                Migrations Available
                            </p>
                            <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${style.badge}`}>
                                {balanceData.migrations_remaining}
                            </span>
                            {refreshing && (
                                <RefreshCw className="w-3 h-3 text-gray-400 animate-spin" />
                            )}
                        </div>

                        {/* Show breakdown by type if available */}
                        {hasCreditsBreakdown ? (
                            <div className="flex flex-wrap gap-2 mt-1">
                                {Object.entries(credits).map(([tierType, info]) => {
                                    if (info.available === 0) return null;
                                    const Icon = TIER_ICONS[tierType] || Zap;
                                    return (
                                        <span
                                            key={tierType}
                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-slate-100 dark:bg-slate-800 rounded text-xs text-slate-700 dark:text-slate-300"
                                            title={`Up to ${formatLimit(info.transaction_limit)} transactions`}
                                        >
                                            <Icon className="w-3 h-3" />
                                            {info.available}x {info.name}
                                            <span className="text-slate-500 dark:text-slate-500">
                                                ({formatLimit(info.transaction_limit)} txn)
                                            </span>
                                        </span>
                                    );
                                })}
                            </div>
                        ) : (
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                {balanceData.migrations_used} used · {balanceData.migrations_purchased} purchased
                            </p>
                        )}
                    </div>
                </div>
                {balanceData.migrations_remaining === 0 ? (
                    <Link
                        href="/select-tier?upgrade=true"
                        className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                    >
                        Buy More
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                ) : (
                    <Link
                        href="/select-tier?upgrade=true"
                        className="flex items-center gap-2 px-4 py-2 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-white rounded-lg hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors text-sm"
                    >
                        Buy More
                    </Link>
                )}
            </div>
        </div>
    );
}
