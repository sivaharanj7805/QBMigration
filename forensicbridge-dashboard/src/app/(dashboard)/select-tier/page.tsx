'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle, Zap, Building2, Shield, Crown, Scale } from 'lucide-react';

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface Tier {
    id: string;
    name: string;
    price: number;
    max_transactions: number;
    description: string;
    migrations: number;
    icon: React.ComponentType<{ className?: string }>;
    popular?: boolean;
}

const TIER_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
    starter: Zap,
    business: Building2,
    professional: Shield,
    enterprise: Crown,
    forensic: Scale
};

export default function TierSelectionPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const isUpgrade = searchParams.get('upgrade') === 'true';

    const [tiers, setTiers] = useState<Tier[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedTier, setSelectedTier] = useState<string | null>(null);
    const [purchasing, setPurchasing] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        loadTiers();
    }, []);

    const loadTiers = async () => {
        try {
            const response = await fetch(`${API_URL}/api/auth/tiers`);
            const data = await response.json();

            if (data.success && data.tiers) {
                const tiersWithIcons = data.tiers.map((tier: Tier) => ({
                    ...tier,
                    icon: TIER_ICONS[tier.id] || Zap,
                    popular: tier.id === 'business'
                }));
                setTiers(tiersWithIcons);
            }
        } catch (err) {
            console.error('Failed to load tiers:', err);
            // Use fallback tiers
            setTiers([
                { id: 'starter', name: 'Starter', price: 497, max_transactions: 5000, description: 'Small business, 1-2 years of data', migrations: 1, icon: Zap },
                { id: 'business', name: 'Business', price: 997, max_transactions: 25000, description: 'Established business, 3-5 years', migrations: 1, icon: Building2, popular: true },
                { id: 'professional', name: 'Professional', price: 1997, max_transactions: 100000, description: 'Complex business, multi-year audit', migrations: 1, icon: Shield },
                { id: 'enterprise', name: 'Enterprise', price: 3997, max_transactions: 500000, description: 'Large company, decade+ of records', migrations: 1, icon: Crown },
                { id: 'forensic', name: 'Forensic', price: 7997, max_transactions: -1, description: 'Litigation-ready, expert documentation', migrations: 1, icon: Scale }
            ]);
        } finally {
            setLoading(false);
        }
    };

    const handleSelectTier = async (tierId: string) => {
        setSelectedTier(tierId);
        setPurchasing(true);
        setError('');

        try {
            const token = localStorage.getItem('token');
            const endpoint = isUpgrade ? '/api/auth/upgrade-tier' : '/api/auth/select-tier';

            const response = await fetch(`${API_URL}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ tier_id: tierId })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to select tier');
            }

            // Success - redirect to dashboard
            router.push('/');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to select tier');
            setSelectedTier(null);
        } finally {
            setPurchasing(false);
        }
    };

    const formatPrice = (price: number) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0
        }).format(price);
    };

    const formatTransactions = (count: number) => {
        if (count === -1) return 'Unlimited';
        if (count >= 1000000) return `${(count / 1000000).toFixed(0)}M+`;
        if (count >= 1000) return `${(count / 1000).toFixed(0)}K`;
        return count.toString();
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 py-12 px-4">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="text-center mb-12">
                    <h1 className="text-4xl font-bold text-white mb-4">
                        {isUpgrade ? 'Purchase Another Migration' : 'Purchase a Migration'}
                    </h1>
                    <p className="text-slate-400 text-lg max-w-2xl mx-auto">
                        Select the migration that matches your QuickBooks file size. Pay once, migrate once. Buy more anytime you need.
                    </p>
                </div>

                {/* Error Message */}
                {error && (
                    <div className="max-w-md mx-auto mb-8 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-center">
                        {error}
                    </div>
                )}

                {/* Tier Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
                    {tiers.map((tier) => {
                        const Icon = tier.icon;
                        const isSelected = selectedTier === tier.id;

                        return (
                            <div
                                key={tier.id}
                                className={`relative rounded-2xl p-6 transition-all duration-300 ${tier.popular
                                    ? 'bg-gradient-to-br from-emerald-600/20 to-teal-600/20 border-2 border-emerald-500/50 scale-105'
                                    : 'bg-slate-800/50 border border-slate-700/50 hover:border-slate-600'
                                    } ${isSelected ? 'ring-2 ring-emerald-500' : ''}`}
                            >
                                {/* Popular Badge */}
                                {tier.popular && (
                                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                                        <span className="bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-full">
                                            MOST POPULAR
                                        </span>
                                    </div>
                                )}

                                {/* Icon */}
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${tier.popular ? 'bg-emerald-500/20' : 'bg-slate-700/50'
                                    }`}>
                                    <Icon className={`w-6 h-6 ${tier.popular ? 'text-emerald-400' : 'text-slate-400'}`} />
                                </div>

                                {/* Name & Price */}
                                <h3 className="text-xl font-bold text-white mb-1">{tier.name}</h3>
                                <div className="mb-4">
                                    <span className="text-3xl font-bold text-white">{formatPrice(tier.price)}</span>
                                    <span className="text-slate-400 text-sm"> / migration</span>
                                </div>

                                {/* Transactions */}
                                <div className="text-sm text-slate-300 mb-4">
                                    Up to <span className="font-semibold text-white">{formatTransactions(tier.max_transactions)}</span> transactions
                                </div>

                                {/* Description */}
                                <p className="text-slate-400 text-sm mb-6">{tier.description}</p>

                                {/* Features */}
                                <ul className="space-y-2 mb-6">
                                    <li className="flex items-center gap-2 text-sm text-slate-300">
                                        <CheckCircle className="w-4 h-4 text-emerald-500" />
                                        1 Migration Included
                                    </li>
                                    <li className="flex items-center gap-2 text-sm text-slate-300">
                                        <CheckCircle className="w-4 h-4 text-emerald-500" />
                                        Forensic Verification
                                    </li>
                                    <li className="flex items-center gap-2 text-sm text-slate-300">
                                        <CheckCircle className="w-4 h-4 text-emerald-500" />
                                        Audit Certificate
                                    </li>
                                    {tier.id === 'enterprise' || tier.id === 'forensic' ? (
                                        <li className="flex items-center gap-2 text-sm text-slate-300">
                                            <CheckCircle className="w-4 h-4 text-emerald-500" />
                                            Team Management
                                        </li>
                                    ) : null}
                                </ul>

                                {/* Select Button */}
                                <button
                                    onClick={() => handleSelectTier(tier.id)}
                                    disabled={purchasing}
                                    className={`w-full py-3 rounded-lg font-medium transition-all ${tier.popular
                                        ? 'bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:from-emerald-600 hover:to-teal-600'
                                        : 'bg-slate-700 text-white hover:bg-slate-600'
                                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                                >
                                    {purchasing && isSelected ? (
                                        <span className="flex items-center justify-center gap-2">
                                            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                            </svg>
                                            Processing...
                                        </span>
                                    ) : (
                                        `Buy ${tier.name} Migration`
                                    )}
                                </button>
                            </div>
                        );
                    })}
                </div>

                {/* Footer Note */}
                <p className="text-center text-slate-500 text-sm mt-12">
                    All migrations include AES-256 encryption, AWS-hosted processing, and audit certificate.
                    <br />
                    Migrations never expire. Buy now, use whenever you're ready.
                </p>
            </div>
        </div>
    );
}
