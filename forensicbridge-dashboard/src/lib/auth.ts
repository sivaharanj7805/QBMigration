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
    role?: string;
}

export interface AuthState {
    user: User | null;
    isAuthenticated: boolean;
}

// CSRF token storage (in-memory only, fetched from server)
let csrfToken: string | null = null;
let csrfTokenExpiry: number | null = null;

// CSRF token validity duration (15 minutes in milliseconds)
const CSRF_TOKEN_VALIDITY_MS = 15 * 60 * 1000;
// Refresh token 2 minutes before expiry
const CSRF_REFRESH_BUFFER_MS = 2 * 60 * 1000;

// AUDIT FIX P2-02: Promise-based queue instead of sleep polling
// Prevents race condition where concurrent requests skip CSRF
let csrfRefreshPromise: Promise<string | null> | null = null;

// AUDIT FIX HIGH-11: Session duration enforcement
const SESSION_MAX_DURATION_MS = 8 * 60 * 60 * 1000; // 8 hours absolute max
const SESSION_INACTIVITY_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes inactivity

// FIX F-02: Use functions to access sessionStorage instead of module-level variables
// This prevents cross-user state bleed in SSR or shared module contexts
function getSessionStartTime(): number | null {
    if (typeof window === 'undefined') return null;
    const val = sessionStorage.getItem('fb_session_start');
    return val ? parseInt(val, 10) : null;
}

function setSessionStartTime(time: number | null): void {
    if (typeof window === 'undefined') return;
    if (time === null) {
        sessionStorage.removeItem('fb_session_start');
    } else {
        sessionStorage.setItem('fb_session_start', String(time));
    }
}

function getLastActivityTime(): number | null {
    if (typeof window === 'undefined') return null;
    const val = sessionStorage.getItem('fb_last_activity');
    return val ? parseInt(val, 10) : null;
}

function setLastActivityTime(time: number | null): void {
    if (typeof window === 'undefined') return;
    if (time === null) {
        sessionStorage.removeItem('fb_last_activity');
    } else {
        sessionStorage.setItem('fb_last_activity', String(time));
    }
}

/**
 * SECURITY: Check if CSRF token is expired or expiring soon
 */
function isCsrfTokenExpired(): boolean {
    if (!csrfToken || !csrfTokenExpiry) return true;
    // Consider expired if within the refresh buffer
    return Date.now() >= (csrfTokenExpiry - CSRF_REFRESH_BUFFER_MS);
}

/**
 * SECURITY: Fetch CSRF token from server
 * Server should provide this via a dedicated endpoint or in response headers
 * Now includes expiration tracking and auto-refresh support
 */
export async function fetchCsrfToken(forceRefresh: boolean = false): Promise<string | null> {
    // Return cached token if valid and not forcing refresh
    if (!forceRefresh && csrfToken && !isCsrfTokenExpired()) {
        return csrfToken;
    }

    // AUDIT FIX P2-02: Use promise-based deduplication instead of sleep polling
    // All concurrent callers await the same in-flight request
    if (csrfRefreshPromise) {
        return csrfRefreshPromise;
    }

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

    csrfRefreshPromise = (async () => {
        try {
            const response = await fetch(`${API_URL}/api/auth/csrf-token`, {
                method: 'GET',
                credentials: 'include',
            });
            if (response.ok) {
                const data = await response.json();
                csrfToken = data.csrf_token || data.csrfToken || null;
                const serverExpiry = data.expires_in ? Date.now() + (data.expires_in * 1000) : null;
                csrfTokenExpiry = serverExpiry || (Date.now() + CSRF_TOKEN_VALIDITY_MS);
                return csrfToken;
            }
        } catch {
            if (process.env.NODE_ENV === 'development') {
                console.warn('[Auth] CSRF token endpoint not available');
            }
        } finally {
            csrfRefreshPromise = null;
        }
        return null;
    })();

    return csrfRefreshPromise;
}

/**
 * SECURITY: Auto-refresh CSRF token if expired
 * Call this before making mutation requests
 */
export async function ensureValidCsrfToken(): Promise<string | null> {
    if (isCsrfTokenExpired()) {
        return fetchCsrfToken(true);
    }
    return csrfToken;
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
    // Set expiry when token is set
    csrfTokenExpiry = token ? Date.now() + CSRF_TOKEN_VALIDITY_MS : null;
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
 * FALLBACK: If token is provided, store it in localStorage for Bearer auth
 * (necessary for localhost/cross-origin where cookies might fail)
 */
export function setAuthState(user: User, csrfTokenValue?: string, token?: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('user', JSON.stringify(user));
    localStorage.setItem('isLoggedIn', 'true');

    // FALLBACK: Store token for Bearer auth if cookies fail
    if (token) {
        localStorage.setItem('auth_token', token);
    }

    // FIX F-02: Use sessionStorage-backed functions for session timers
    setSessionStartTime(Date.now());
    setLastActivityTime(Date.now());
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
    localStorage.removeItem('auth_token'); // Clear fallback token
    csrfToken = null;
    csrfTokenExpiry = null;
    // FIX F-02: Clear sessionStorage-backed session timers
    setSessionStartTime(null);
    setLastActivityTime(null);
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
    // Auto-refresh expired CSRF token before mutation to prevent 403 rejections
    const method = (options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
        const token = await ensureValidCsrfToken();
        if (token) {
            headers.set('X-CSRF-Token', token);
        }
    }

    // FALLBACK: Add Bearer token if available (in case cookies failed)
    // This allows auth to work even if httpOnly cookies are blocked/dropped
    if (typeof window !== 'undefined') {
        const authToken = localStorage.getItem('auth_token');
        if (authToken) {
            headers.set('Authorization', `Bearer ${authToken}`);
        }
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
    // AUDIT FIX HIGH-11: Check client-side session expiry first
    if (isSessionExpired()) {
        clearAuth();
        return false;
    }

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
    try {
        const response = await authFetch(`${API_URL}/api/auth/validate`, {
            method: 'GET',
        });
        if (response.ok) {
            updateActivityTime();
        }
        return response.ok;
    } catch {
        return false;
    }
}

/**
 * AUDIT FIX HIGH-11: Update last activity timestamp for inactivity tracking
 */
export function updateActivityTime(): void {
    setLastActivityTime(Date.now());
}

/**
 * FIX F-02: Check session expiry using sessionStorage-backed timers
 */
export function isSessionExpired(): boolean {
    const sessionStart = getSessionStartTime();
    const lastActivity = getLastActivityTime();
    if (!sessionStart || !lastActivity) return false; // No session yet
    const now = Date.now();
    // Check absolute session duration (8 hours)
    if (now - sessionStart > SESSION_MAX_DURATION_MS) return true;
    // Check inactivity timeout (30 minutes)
    if (now - lastActivity > SESSION_INACTIVITY_TIMEOUT_MS) return true;
    return false;
}
