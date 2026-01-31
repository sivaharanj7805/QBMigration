/**
 * Authentication helpers for ForensicBridge dashboard
 *
 * SECURITY FIX: Uses httpOnly cookies via credentials: 'include' instead of localStorage
 * This prevents XSS attacks from accessing tokens directly.
 *
 * The server must set httpOnly cookies on login/register responses.
 * This client only tracks user info (non-sensitive) in memory/localStorage.
 */

export interface User {
    id: number;
    email: string;
    name?: string;           // Frontend format
    first_name?: string;     // Backend format
    last_name?: string;      // Backend format
    company?: string;        // Frontend format
    company_name?: string;   // Backend format
}

export interface AuthState {
    user: User | null;
    isAuthenticated: boolean;
}

// CSRF token storage (in-memory only, fetched from server)
let csrfToken: string | null = null;

/**
 * SECURITY: Fetch CSRF token from server
 * Server should provide this via a dedicated endpoint or in response headers
 */
export async function fetchCsrfToken(): Promise<string | null> {
    if (csrfToken) return csrfToken;

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
    try {
        const response = await fetch(`${API_URL}/api/auth/csrf-token`, {
            method: 'GET',
            credentials: 'include',
        });
        if (response.ok) {
            const data = await response.json();
            csrfToken = data.csrf_token || data.csrfToken || null;
            return csrfToken;
        }
    } catch {
        // CSRF endpoint may not exist yet - continue without it
        if (process.env.NODE_ENV === 'development') {
            console.warn('[Auth] CSRF token endpoint not available');
        }
    }
    return null;
}

/**
 * Get CSRF token (synchronous, returns cached value)
 */
export function getCsrfToken(): string | null {
    return csrfToken;
}

/**
 * Set CSRF token (from response headers or body)
 */
export function setCsrfToken(token: string | null): void {
    csrfToken = token;
}

/**
 * Get current auth state
 * SECURITY: Only user info is stored locally, not tokens
 * The actual auth token is in an httpOnly cookie managed by the browser
 */
export function getAuthState(): AuthState {
    if (typeof window === 'undefined') {
        return { user: null, isAuthenticated: false };
    }

    const userStr = localStorage.getItem('user');
    const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';

    let user: User | null = null;
    if (userStr) {
        try {
            user = JSON.parse(userStr);
        } catch {
            user = null;
        }
    }

    return {
        user,
        isAuthenticated: isLoggedIn && !!user,
    };
}

/**
 * Set auth state after login/register
 * SECURITY: Only stores user info, not the token
 * The token should be set as an httpOnly cookie by the server
 */
export function setAuthState(user: User, csrfTokenValue?: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('isLoggedIn', 'true');
    if (csrfTokenValue) {
        setCsrfToken(csrfTokenValue);
    }
}

/**
 * Clear auth state (logout)
 */
export function clearAuth(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('user');
    localStorage.removeItem('isLoggedIn');
    csrfToken = null;
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
    return getAuthState().isAuthenticated;
}

/**
 * Redirect to login if not authenticated
 */
export function requireAuth(): boolean {
    if (!isAuthenticated()) {
        if (typeof window !== 'undefined') {
            window.location.href = '/login';
        }
        return false;
    }
    return true;
}

/**
 * Get standard headers for API requests
 * SECURITY: Includes CSRF token for mutation requests
 */
export function getAuthHeader(includeCsrf: boolean = false): Record<string, string> {
    const headers: Record<string, string> = {};
    if (includeCsrf && csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
    }
    return headers;
}

/**
 * Request timeout constant
 */
const DEFAULT_REQUEST_TIMEOUT = 30000; // 30 seconds

/**
 * Fetch wrapper with automatic auth header, CSRF token, and error handling
 * SECURITY: Uses credentials: 'include' to send httpOnly cookies
 * SECURITY: Includes CSRF token for non-GET requests
 * SECURITY: Adds request timeout via AbortController
 */
export async function authFetch(
    url: string,
    options: RequestInit = {},
    timeout: number = DEFAULT_REQUEST_TIMEOUT
): Promise<Response> {
    // Create AbortController for timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const headers = new Headers(options.headers);

    // Add Content-Type if not set
    if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    // SECURITY: Add CSRF token for non-GET requests
    const method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && csrfToken) {
        headers.set('X-CSRF-Token', csrfToken);
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include', // SECURITY: Send httpOnly cookies
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        // Extract CSRF token from response header if provided
        const newCsrfToken = response.headers.get('X-CSRF-Token');
        if (newCsrfToken) {
            setCsrfToken(newCsrfToken);
        }

        // Handle 401 by clearing auth and redirecting
        if (response.status === 401) {
            clearAuth();
            if (typeof window !== 'undefined') {
                window.location.href = '/login';
            }
        }

        return response;
    } catch (error) {
        clearTimeout(timeoutId);

        // Check if it was a timeout
        if (error instanceof Error && error.name === 'AbortError') {
            throw new Error(`Request timed out after ${timeout / 1000} seconds`);
        }

        throw error;
    }
}

/**
 * Validate session with server
 * Returns true if session is valid, false otherwise
 */
export async function validateSession(): Promise<boolean> {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
    try {
        const response = await authFetch(`${API_URL}/api/auth/validate`, {
            method: 'GET',
        });
        return response.ok;
    } catch {
        return false;
    }
}
