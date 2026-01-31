'use client';

import { useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { setAuthState, setCsrfToken } from '@/lib/auth';
import { sanitize } from '@/lib/sanitize';

// API configuration - must be set in environment
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

/**
 * Password validation requirements
 * SECURITY: Strong password policy - min 12 chars, uppercase, lowercase, numbers, symbols
 */
interface PasswordValidation {
    isValid: boolean;
    errors: string[];
    strength: 'weak' | 'fair' | 'good' | 'strong';
    requirements: {
        minLength: boolean;
        hasUppercase: boolean;
        hasLowercase: boolean;
        hasNumber: boolean;
        hasSymbol: boolean;
        noCommonPatterns: boolean;
    };
}

/**
 * Validate password strength
 * SECURITY FIX: Comprehensive password validation
 */
function validatePassword(password: string): PasswordValidation {
    const requirements = {
        minLength: password.length >= 12,
        hasUppercase: /[A-Z]/.test(password),
        hasLowercase: /[a-z]/.test(password),
        hasNumber: /[0-9]/.test(password),
        hasSymbol: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?`~]/.test(password),
        noCommonPatterns: !isCommonPassword(password),
    };

    const errors: string[] = [];
    if (!requirements.minLength) errors.push('At least 12 characters');
    if (!requirements.hasUppercase) errors.push('At least one uppercase letter');
    if (!requirements.hasLowercase) errors.push('At least one lowercase letter');
    if (!requirements.hasNumber) errors.push('At least one number');
    if (!requirements.hasSymbol) errors.push('At least one special character (!@#$%^&*...)');
    if (!requirements.noCommonPatterns) errors.push('Avoid common patterns');

    const passedCount = Object.values(requirements).filter(Boolean).length;
    let strength: 'weak' | 'fair' | 'good' | 'strong' = 'weak';
    if (passedCount >= 6) strength = 'strong';
    else if (passedCount >= 5) strength = 'good';
    else if (passedCount >= 3) strength = 'fair';

    return {
        isValid: errors.length === 0,
        errors,
        strength,
        requirements,
    };
}

/**
 * Check for common password patterns
 * SECURITY FIX: Corrected logic - only check if password contains common patterns
 * or if password is too similar to a common pattern (not the reverse)
 */
function isCommonPassword(password: string): boolean {
    const commonPatterns = [
        'password', '123456', 'qwerty', 'abc123', 'letmein',
        'admin', 'welcome', 'monkey', 'dragon', 'master',
        '12345678', '123456789', '1234567890', 'password1',
    ];

    const lower = password.toLowerCase();

    // Check if password contains any common pattern
    // OR if password is essentially the same as a common pattern (exact match)
    // FIX: Removed pattern.includes(lower) which incorrectly flags short passwords
    return commonPatterns.some(pattern =>
        lower.includes(pattern) || lower === pattern
    );
}

/**
 * Password strength indicator component
 */
function PasswordStrengthIndicator({ validation }: { validation: PasswordValidation }) {
    const strengthColors = {
        weak: 'bg-red-500',
        fair: 'bg-yellow-500',
        good: 'bg-blue-500',
        strong: 'bg-green-500',
    };

    const strengthWidth = {
        weak: '25%',
        fair: '50%',
        good: '75%',
        strong: '100%',
    };

    return (
        <div className="mt-2">
            {/* Strength bar */}
            <div className="h-1 bg-slate-700 rounded-full overflow-hidden">
                <div
                    className={`h-full ${strengthColors[validation.strength]} transition-all duration-300`}
                    style={{ width: strengthWidth[validation.strength] }}
                />
            </div>

            {/* Strength label */}
            <p className="text-xs mt-1 text-slate-400">
                Password strength:{' '}
                <span className={
                    validation.strength === 'strong' ? 'text-green-400' :
                    validation.strength === 'good' ? 'text-blue-400' :
                    validation.strength === 'fair' ? 'text-yellow-400' :
                    'text-red-400'
                }>
                    {validation.strength.charAt(0).toUpperCase() + validation.strength.slice(1)}
                </span>
            </p>

            {/* Requirements checklist */}
            <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
                <RequirementItem met={validation.requirements.minLength} text="12+ characters" />
                <RequirementItem met={validation.requirements.hasUppercase} text="Uppercase letter" />
                <RequirementItem met={validation.requirements.hasLowercase} text="Lowercase letter" />
                <RequirementItem met={validation.requirements.hasNumber} text="Number" />
                <RequirementItem met={validation.requirements.hasSymbol} text="Special character" />
                <RequirementItem met={validation.requirements.noCommonPatterns} text="No common patterns" />
            </div>
        </div>
    );
}

function RequirementItem({ met, text }: { met: boolean; text: string }) {
    return (
        <div className={`flex items-center gap-1 ${met ? 'text-green-400' : 'text-slate-500'}`}>
            <span>{met ? '✓' : '○'}</span>
            <span>{text}</span>
        </div>
    );
}

export default function RegisterPage() {
    const router = useRouter();
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [company, setCompany] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [showPasswordRequirements, setShowPasswordRequirements] = useState(false);

    // Memoized password validation
    const passwordValidation = useMemo(() => validatePassword(password), [password]);

    // Form validation
    const validateForm = useCallback((): string | null => {
        // Sanitize inputs
        const sanitizedName = sanitize.text(name);
        const sanitizedEmail = sanitize.text(email);

        if (!sanitizedName || sanitizedName.length < 2) {
            return 'Please enter your full name';
        }

        if (!sanitizedEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(sanitizedEmail)) {
            return 'Please enter a valid email address';
        }

        // Password validation
        if (!passwordValidation.isValid) {
            return `Password requirements not met: ${passwordValidation.errors.join(', ')}`;
        }

        // Confirm password
        if (password !== confirmPassword) {
            return 'Passwords do not match';
        }

        return null;
    }, [name, email, password, confirmPassword, passwordValidation]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        // Validate form
        const validationError = validateForm();
        if (validationError) {
            setError(validationError);
            return;
        }

        setLoading(true);

        try {
            // SECURITY: Using credentials: 'include' for httpOnly cookie support
            const response = await fetch(`${API_URL}/api/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    name: sanitize.text(name),
                    email: sanitize.text(email),
                    password,
                    company: sanitize.text(company),
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Registration failed');
            }

            // SECURITY: Store only user info, not token (token is in httpOnly cookie)
            if (data.user) {
                setAuthState(data.user, data.csrf_token);
            }

            // If server still sends token (backward compatibility), set CSRF token
            if (data.csrf_token) {
                setCsrfToken(data.csrf_token);
            }

            // Redirect to tier selection (new users need to pick a tier)
            router.push('/select-tier');
        } catch (err) {
            if (err instanceof TypeError && err.message === 'Failed to fetch') {
                setError('Cannot connect to server. Please check if the API is running.');
            } else {
                setError(err instanceof Error ? err.message : 'Registration failed');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 py-12">
            <div className="w-full max-w-md px-4">
                {/* Logo */}
                <div className="text-center mb-8">
                    <div className="flex justify-center mb-4">
                        <Image
                            src="/new-logo.png"
                            alt="ForensicBridge"
                            width={120}
                            height={120}
                            className="rounded-xl"
                        />
                    </div>
                    <h1 className="text-3xl font-bold text-white mb-2">ForensicBridge</h1>
                    <p className="text-slate-400">Create your account</p>
                    <a
                        href="https://forensicbridge.ca"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-amber-500 hover:text-amber-400 text-sm mt-1 inline-block"
                    >
                        forensicbridge.ca
                    </a>
                </div>

                {/* Register Card */}
                <div className="bg-slate-800/50 backdrop-blur-xl rounded-2xl p-8 shadow-2xl border border-slate-700/50">
                    <h2 className="text-xl font-semibold text-white mb-6">Get Started</h2>

                    {error && (
                        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="name" className="block text-sm font-medium text-slate-300 mb-2">
                                Full Name
                            </label>
                            <input
                                id="name"
                                name="name"
                                type="text"
                                autoComplete="name"
                                value={name}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
                                required
                                aria-required="true"
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="John Smith"
                            />
                        </div>

                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-2">
                                Email Address
                            </label>
                            <input
                                id="email"
                                name="email"
                                type="email"
                                autoComplete="email"
                                value={email}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                                required
                                aria-required="true"
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="you@company.com"
                            />
                        </div>

                        <div>
                            <label htmlFor="company" className="block text-sm font-medium text-slate-300 mb-2">
                                Company Name
                            </label>
                            <input
                                id="company"
                                name="company"
                                type="text"
                                autoComplete="organization"
                                value={company}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCompany(e.target.value)}
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="Acme CPA Firm"
                            />
                        </div>

                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-2">
                                Password
                            </label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                autoComplete="new-password"
                                value={password}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                                onFocus={() => setShowPasswordRequirements(true)}
                                required
                                aria-required="true"
                                aria-describedby="password-requirements"
                                minLength={12}
                                className="w-full px-4 py-3 rounded-lg bg-slate-900/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all"
                                placeholder="Min 12 characters"
                            />
                            {/* Password strength indicator */}
                            {showPasswordRequirements && password.length > 0 && (
                                <div id="password-requirements">
                                    <PasswordStrengthIndicator validation={passwordValidation} />
                                </div>
                            )}
                        </div>

                        <div>
                            <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-300 mb-2">
                                Confirm Password
                            </label>
                            <input
                                id="confirmPassword"
                                name="confirmPassword"
                                type="password"
                                autoComplete="new-password"
                                value={confirmPassword}
                                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                                required
                                aria-required="true"
                                minLength={12}
                                className={`w-full px-4 py-3 rounded-lg bg-slate-900/50 border text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all ${
                                    confirmPassword && password !== confirmPassword
                                        ? 'border-red-500'
                                        : confirmPassword && password === confirmPassword
                                        ? 'border-green-500'
                                        : 'border-slate-600'
                                }`}
                                placeholder="Confirm your password"
                            />
                            {confirmPassword && password !== confirmPassword && (
                                <p className="text-red-400 text-xs mt-1">Passwords do not match</p>
                            )}
                            {confirmPassword && password === confirmPassword && (
                                <p className="text-green-400 text-xs mt-1">Passwords match</p>
                            )}
                        </div>

                        <button
                            type="submit"
                            disabled={loading || !passwordValidation.isValid || password !== confirmPassword}
                            className="w-full py-3 px-4 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-500 text-white font-medium hover:from-emerald-600 hover:to-teal-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        >
                            {loading ? (
                                <span className="flex items-center justify-center gap-2">
                                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                    </svg>
                                    Creating account...
                                </span>
                            ) : (
                                'Create Account'
                            )}
                        </button>
                    </form>

                    <div className="mt-6 text-center">
                        <p className="text-slate-400 text-sm">
                            Already have an account?{' '}
                            <Link href="/login" className="text-emerald-400 hover:text-emerald-300 font-medium">
                                Sign in
                            </Link>
                        </p>
                    </div>
                </div>

                {/* Footer */}
                <p className="mt-8 text-center text-slate-500 text-sm">
                    By creating an account, you agree to our <a href="https://forensicbridge.ca/terms" target="_blank" rel="noopener noreferrer" className="hover:text-slate-400">Terms of Service</a>
                </p>
            </div>
        </div>
    );
}
