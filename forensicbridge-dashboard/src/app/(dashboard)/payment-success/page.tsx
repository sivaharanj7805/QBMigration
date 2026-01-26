'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle } from 'lucide-react';

export default function PaymentSuccessPage() {
    const router = useRouter();

    useEffect(() => {
        // Redirect to dashboard after a brief delay
        const timer = setTimeout(() => {
            router.push('/');
        }, 2000);

        return () => clearTimeout(timer);
    }, [router]);

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
            <div className="max-w-md w-full bg-slate-800/50 border border-slate-700/50 rounded-2xl p-8 text-center">
                <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-emerald-500/20 flex items-center justify-center">
                    <CheckCircle className="w-8 h-8 text-emerald-500" />
                </div>
                <h1 className="text-2xl font-bold text-white mb-2">Plan Selected!</h1>
                <p className="text-slate-400">
                    Redirecting to dashboard...
                </p>
            </div>
        </div>
    );
}
