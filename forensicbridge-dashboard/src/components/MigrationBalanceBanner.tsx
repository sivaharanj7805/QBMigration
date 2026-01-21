'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { AlertCircle, Package, ArrowRight } from 'lucide-react';
import { getAuthState } from '@/lib/auth';

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface MigrationBalanceData {
    tier: string;
    tier_name: string;
    migrations_remaining: number;
    migrations_purchased: number;
    migrations_used: number;
    has_tier: boolean;
}

export function MigrationBalanceBanner() {
    const [balanceData, setBalanceData] = useState<MigrationBalanceData | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadBalanceData();
    }, []);

    const loadBalanceData = async () => {
        try {
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
                        has_tier: data.user.has_tier || false
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load balance data:', error);
        } finally {
            setLoading(false);
        }
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
                                No migration plan selected
                            </p>
                            <p className="text-sm text-amber-600 dark:text-amber-400">
                                Select a tier to start migrating your QuickBooks data
                            </p>
                        </div>
                    </div>
                    <Link
                        href="/select-tier"
                        className="flex items-center gap-2 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors"
                    >
                        Choose Plan
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                </div>
            </div>
        );
    }

    // Get appropriate color based on remaining migrations
    const getBalanceColor = () => {
        if (balanceData.migrations_remaining === 0) return 'red';
        if (balanceData.migrations_remaining <= 1) return 'amber';
        return 'emerald';
    };

    const color = getBalanceColor();

    return (
        <div className={`bg-${color}-500/10 border border-${color}-500/30 rounded-lg p-4 mb-6`}>
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Package className={`w-5 h-5 text-${color}-500`} />
                    <div>
                        <p className="font-medium text-gray-900 dark:text-white">
                            {balanceData.migrations_remaining} {balanceData.tier_name} migration{balanceData.migrations_remaining !== 1 ? 's' : ''} left
                        </p>
                        <p className="text-sm text-gray-600 dark:text-gray-400">
                            {balanceData.migrations_used} of {balanceData.migrations_purchased} migrations used
                        </p>
                    </div>
                </div>
                {balanceData.migrations_remaining === 0 && (
                    <Link
                        href="/select-tier?upgrade=true"
                        className="flex items-center gap-2 px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                    >
                        Purchase Migrations
                        <ArrowRight className="w-4 h-4" />
                    </Link>
                )}
            </div>
        </div>
    );
}
