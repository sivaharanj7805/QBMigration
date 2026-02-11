/**
 * Security and utility hooks for ForensicBridge dashboard
 *
 * Includes:
 * - useCsrfToken: CSRF token management
 * - useDebouncedValue: Debouncing for search inputs
 * - useAbortController: Request cancellation
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchCsrfToken, getCsrfToken } from '@/lib/auth';

/**
 * CSRF Token Hook
 * Fetches and provides CSRF token for secure form submissions
 */
export function useCsrfToken() {
    const [token, setToken] = useState<string | null>(getCsrfToken());
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const newToken = await fetchCsrfToken();
            setToken(newToken);
            return newToken;
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Failed to fetch CSRF token';
            setError(errorMessage);
            return null;
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!token) {
            refresh();
        }
    }, [token, refresh]);

    return { token, loading, error, refresh };
}

/**
 * Debounced Value Hook
 * Delays updating a value until after a specified delay
 * Useful for search inputs to prevent excessive API calls
 */
export function useDebouncedValue<T>(value: T, delay: number = 300): T {
    const [debouncedValue, setDebouncedValue] = useState<T>(value);

    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedValue(value);
        }, delay);

        return () => {
            clearTimeout(timer);
        };
    }, [value, delay]);

    return debouncedValue;
}

/**
 * Debounced Callback Hook
 * Creates a debounced version of a callback function
 *
 * MEDIUM FIX: Corrected generic type signature to avoid circular reference
 * Original: T extends (...args: Parameters<T>) => ReturnType<T> (circular)
 * Fixed: Use explicit Args and R generic parameters
 */
export function useDebouncedCallback<Args extends unknown[], R>(
    callback: (...args: Args) => R,
    delay: number = 300
): (...args: Args) => void {
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        return () => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current);
            }
        };
    }, []);

    return useCallback(
        (...args: Args) => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current);
            }
            timeoutRef.current = setTimeout(() => {
                callback(...args);
            }, delay);
        },
        [callback, delay]
    );
}

/**
 * AbortController Hook
 * Provides an AbortController that automatically aborts on unmount
 * Useful for cancelling API requests when component unmounts
 */
export function useAbortController(): AbortController {
    const controllerRef = useRef<AbortController>(new AbortController());

    useEffect(() => {
        // Create new controller on mount
        controllerRef.current = new AbortController();

        return () => {
            // Abort on unmount
            controllerRef.current.abort();
        };
    }, []);

    return controllerRef.current;
}

/**
 * Abort Signal Hook
 * PERFORMANCE FIX: Creates AbortController once per mount, not on every render
 * Automatically aborts on unmount to prevent memory leaks
 *
 * Note: If you need to abort/refresh mid-lifecycle, use useAbortController instead
 * and call controller.abort() manually when needed.
 */
export function useAbortSignal(): AbortSignal {
    // MED-21 FIX: Create controller only once via lazy ref init (removed duplicate in useEffect)
    const controllerRef = useRef<AbortController | null>(null);

    if (controllerRef.current === null) {
        controllerRef.current = new AbortController();
    }

    useEffect(() => {
        return () => {
            // Abort on unmount to prevent memory leaks
            controllerRef.current?.abort();
        };
    }, []);

    return controllerRef.current.signal;
}

/**
 * Loading Guard Hook
 * Prevents double-clicks and race conditions in async operations
 */
export function useLoadingGuard() {
    const [isLoading, setIsLoading] = useState(false);
    // MED-20 FIX: Use ref for loading guard to avoid stale closure over isLoading state
    const isLoadingRef = useRef(false);
    const operationIdRef = useRef(0);

    const execute = useCallback(async <T>(
        operation: (signal: AbortSignal) => Promise<T>
    ): Promise<T | null> => {
        if (isLoadingRef.current) {
            return null; // Prevent double execution
        }

        isLoadingRef.current = true;
        const currentId = ++operationIdRef.current;
        const controller = new AbortController();

        setIsLoading(true);
        try {
            const result = await operation(controller.signal);
            if (currentId === operationIdRef.current) {
                return result;
            }
            return null;
        } catch (error) {
            if (currentId === operationIdRef.current) {
                throw error;
            }
            return null;
        } finally {
            if (currentId === operationIdRef.current) {
                isLoadingRef.current = false;
                setIsLoading(false);
            }
        }
    }, []);

    const cancel = useCallback(() => {
        operationIdRef.current++;
        setIsLoading(false);
    }, []);

    return { isLoading, execute, cancel };
}

/**
 * Polling Hook with Backoff
 * Polls a function at regular intervals with exponential backoff on errors
 * Stops polling when a terminal condition is met
 */
export function usePollingWithBackoff<T>(
    pollFn: () => Promise<T>,
    options: {
        interval: number;
        maxInterval?: number;
        backoffMultiplier?: number;
        isTerminal?: (data: T) => boolean;
        enabled?: boolean;
        onError?: (error: Error) => void;
    }
) {
    const {
        interval,
        maxInterval = 30000,
        backoffMultiplier = 2,
        isTerminal = () => false,
        enabled = true,
        onError,
    } = options;

    const [data, setData] = useState<T | null>(null);
    const [error, setError] = useState<Error | null>(null);
    const [isPolling, setIsPolling] = useState(enabled);
    const currentIntervalRef = useRef(interval);
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);

    const poll = useCallback(async () => {
        if (!enabled || !isPolling) return;

        try {
            const result = await pollFn();
            setData(result);
            setError(null);
            currentIntervalRef.current = interval; // Reset backoff on success

            if (isTerminal(result)) {
                setIsPolling(false);
                return;
            }
        } catch (err) {
            const error = err instanceof Error ? err : new Error(String(err));
            setError(error);
            onError?.(error);

            // Apply backoff
            currentIntervalRef.current = Math.min(
                currentIntervalRef.current * backoffMultiplier,
                maxInterval
            );
        }

        // Schedule next poll
        timeoutRef.current = setTimeout(poll, currentIntervalRef.current);
    }, [enabled, isPolling, pollFn, interval, maxInterval, backoffMultiplier, isTerminal, onError]);

    useEffect(() => {
        if (enabled && isPolling) {
            poll();
        }

        return () => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current);
            }
        };
    }, [enabled, isPolling, poll]);

    const stop = useCallback(() => {
        setIsPolling(false);
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current);
        }
    }, []);

    const restart = useCallback(() => {
        currentIntervalRef.current = interval;
        setIsPolling(true);
    }, [interval]);

    return { data, error, isPolling, stop, restart };
}
