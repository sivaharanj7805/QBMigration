/**
 * Vitest Test Setup
 * Global setup for frontend tests
 */

import '@testing-library/jest-dom';

// Mock window.matchMedia for responsive tests
Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => { },
        removeListener: () => { },
        addEventListener: () => { },
        removeEventListener: () => { },
        dispatchEvent: () => false,
    }),
});

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
    observe() { }
    unobserve() { }
    disconnect() { }
};

// Mock fetch for API tests
global.fetch = async (url: string, options?: RequestInit) => {
    return new Response(JSON.stringify({ success: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });
};

// Suppress console errors during tests
const originalError = console.error;
console.error = (...args: any[]) => {
    if (
        typeof args[0] === 'string' &&
        args[0].includes('Warning: ReactDOM.render is no longer supported')
    ) {
        return;
    }
    originalError.call(console, ...args);
};
