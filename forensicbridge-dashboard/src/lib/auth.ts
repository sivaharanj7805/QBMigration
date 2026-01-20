/**
 * Authentication helpers for ForensicBridge dashboard
 */

export interface User {
    id: number;
    email: string;
    name: string;
    company?: string;
}

export interface AuthState {
    token: string | null;
    user: User | null;
    isAuthenticated: boolean;
}

/**
 * Get current auth state from localStorage
 */
export function getAuthState(): AuthState {
    if (typeof window === 'undefined') {
        return { token: null, user: null, isAuthenticated: false };
    }

    const token = localStorage.getItem('token');
    const userStr = localStorage.getItem('user');

    let user: User | null = null;
    if (userStr) {
        try {
            user = JSON.parse(userStr);
        } catch {
            user = null;
        }
    }

    return {
        token,
        user,
        isAuthenticated: !!token && !!user,
    };
}

/**
 * Get authorization header for API requests
 */
export function getAuthHeader(): Record<string, string> {
    const { token } = getAuthState();
    if (!token) return {};
    return { Authorization: `Bearer ${token}` };
}

/**
 * Clear auth state (logout)
 */
export function clearAuth(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
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
 * Fetch wrapper with automatic auth header and error handling
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const { token } = getAuthState();

    const headers = new Headers(options.headers);
    if (token) {
        headers.set('Authorization', `Bearer ${token}`);
    }
    if (!headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(url, { ...options, headers });

    // Handle 401 by clearing auth and redirecting
    if (response.status === 401) {
        clearAuth();
        if (typeof window !== 'undefined') {
            window.location.href = '/login';
        }
    }

    return response;
}
