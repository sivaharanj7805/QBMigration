'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle, Loader2, XCircle, ArrowRight } from 'lucide-react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function PaymentSuccessPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const sessionId = searchParams.get('session_id');

    const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
    const [message, setMessage] = useState('');
    const [creditInfo, setCreditInfo] = useState<{
        tier_name: string;
        transaction_limit: number;
    } | null>(null);

    useEffect(() => {
        if (sessionId) {
            verifyPayment();
        } else {
            setStatus('error');
            setMessage('No session ID provided');
        }
    }, [sessionId]);

    const verifyPayment = async () => {
        try {
            const token = localStorage.getItem('token');

            const response = await fetch(`${API_URL}/api/payments/verify-session/${sessionId}`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            const data = await response.json();

            if (data.success && data.is_paid) {
                setStatus('success');
                setMessage('Your migration credit has been added to your account!');
                setCreditInfo({
                    tier_name: data.credit?.tier_name || 'Migration',
                    transaction_limit: data.credit?.transaction_limit || 0
                });
            } else if (data.success && !data.is_paid) {
                // Payment may still be processing
                setStatus('loading');
                setMessage('Payment is being processed...');
                // Retry after a few seconds
                setTimeout(verifyPayment, 3000);
            } else {
                setStatus('error');
                setMessage(data.error || 'Payment verification failed');
            }
        } catch (error) {
            console.error('Verification error:', error);
            setStatus('error');
            setMessage('Failed to verify payment. Please contact support.');
        }
    };

    const formatLimit = (limit: number) => {
        if (limit === -1) return 'Unlimited';
        if (limit >= 1000000) return `${(limit / 1000000).toFixed(0)}M`;
        if (limit >= 1000) return `${(limit / 1000).toFixed(0)}K`;
        return limit.toString();
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
            <div className="max-w-md w-full bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
                {status === 'loading' && (
                    <>
                        <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-blue-500/20 flex items-center justify-center">
                            <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                        </div>
                        <h1 className="text-2xl font-bold text-white mb-2">Processing Payment</h1>
                        <p className="text-slate-400">
                            {message || 'Please wait while we verify your payment...'}
                        </p>
                    </>
                )}

                {status === 'success' && (
                    <>
                        <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-emerald-500/20 flex items-center justify-center">
                            <CheckCircle className="w-8 h-8 text-emerald-500" />
                        </div>
                        <h1 className="text-2xl font-bold text-white mb-2">Payment Successful!</h1>
                        <p className="text-slate-400 mb-6">{message}</p>

                        {creditInfo && (
                            <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-4 mb-6">
                                <p className="text-emerald-400 font-medium text-lg">
                                    {creditInfo.tier_name} Migration
                                </p>
                                <p className="text-slate-400 text-sm">
                                    Up to {formatLimit(creditInfo.transaction_limit)} transactions
                                </p>
                            </div>
                        )}

                        <Link
                            href="/"
                            className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 text-white rounded-lg font-medium hover:from-emerald-600 hover:to-teal-600 transition-colors"
                        >
                            Go to Dashboard
                            <ArrowRight className="w-4 h-4" />
                        </Link>
                    </>
                )}

                {status === 'error' && (
                    <>
                        <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-red-500/20 flex items-center justify-center">
                            <XCircle className="w-8 h-8 text-red-500" />
                        </div>
                        <h1 className="text-2xl font-bold text-white mb-2">Payment Issue</h1>
                        <p className="text-slate-400 mb-6">{message}</p>

                        <div className="flex gap-3 justify-center">
                            <Link
                                href="/select-tier"
                                className="px-6 py-3 bg-slate-700 text-white rounded-lg font-medium hover:bg-slate-600 transition-colors"
                            >
                                Try Again
                            </Link>
                            <Link
                                href="/"
                                className="px-6 py-3 bg-emerald-500 text-white rounded-lg font-medium hover:bg-emerald-600 transition-colors"
                            >
                                Dashboard
                            </Link>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
