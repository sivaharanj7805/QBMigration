/**
 * Input Sanitization Utilities for ForensicBridge Dashboard
 *
 * Provides XSS protection for user-generated content before rendering.
 * Uses DOMPurify for HTML sanitization when available, with safe fallbacks.
 *
 * @module lib/sanitize
 *
 * @example
 * ```tsx
 * import { sanitize } from '@/lib/sanitize';
 *
 * // Sanitize user input before display
 * <span>{sanitize.text(userInput)}</span>
 *
 * // Sanitize URLs
 * <a href={sanitize.url(userProvidedUrl)}>Link</a>
 *
 * // Sanitize filenames for downloads
 * const safeFilename = sanitize.filename(userFilename);
 * ```
 */

// Note: DOMPurify must be installed: npm install dompurify @types/dompurify
// For now, we provide a safe fallback that escapes HTML

/**
 * HTML entity map for escaping special characters.
 * Covers all characters that could be used for XSS attacks.
 * @internal
 */
const HTML_ENTITIES: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '`': '&#x60;',
    '=': '&#x3D;',
};

/**
 * Escapes HTML entities to prevent XSS attacks.
 *
 * Converts special HTML characters to their entity equivalents,
 * making the string safe for insertion into HTML content.
 *
 * @param str - The string to escape
 * @returns The escaped string safe for HTML insertion
 *
 * @example
 * ```ts
 * escapeHtml('<script>alert("xss")</script>')
 * // Returns: '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
 * ```
 */
export function escapeHtml(str: string): string {
    if (typeof str !== 'string') {
        return '';
    }
    return str.replace(/[&<>"'`=]/g, (char) => HTML_ENTITIES[char] || char);
}

/**
 * Sanitizes user input for safe display in the UI.
 *
 * Removes potentially dangerous content (null bytes, scripts)
 * while preserving safe text formatting.
 *
 * @param input - The user input to sanitize (can be null/undefined)
 * @returns The sanitized string, or empty string if input is falsy
 *
 * @example
 * ```ts
 * sanitizeText('Hello <script>evil()</script> World')
 * // Returns: 'Hello &lt;script&gt;evil()&lt;/script&gt; World'
 * ```
 */
export function sanitizeText(input: string | null | undefined): string {
    if (!input || typeof input !== 'string') {
        return '';
    }

    // Trim whitespace
    let sanitized = input.trim();

    // Remove null bytes
    sanitized = sanitized.replace(/\0/g, '');

    // Escape HTML entities
    sanitized = escapeHtml(sanitized);

    return sanitized;
}

/**
 * Sanitize HTML content (for rich text)
 * Allows safe HTML tags while removing dangerous ones
 */
export function sanitizeHtml(html: string | null | undefined): string {
    if (!html || typeof html !== 'string') {
        return '';
    }

    // Try to use DOMPurify if available
    if (typeof window !== 'undefined') {
        try {
            // Dynamic import for DOMPurify
            const DOMPurify = (window as Window & { DOMPurify?: { sanitize: (html: string) => string } }).DOMPurify;
            if (DOMPurify) {
                return DOMPurify.sanitize(html);
            }
        } catch {
            // DOMPurify not available, fall through to basic sanitization
        }
    }

    // Fallback: When DOMPurify is not available, escape all HTML.
    // Regex-based sanitization is inherently bypassable, so escaping is safer.
    return escapeHtml(html);
}

/**
 * Sanitize URL to prevent javascript: and data: URLs
 */
export function sanitizeUrl(url: string | null | undefined): string {
    if (!url || typeof url !== 'string') {
        return '';
    }

    const trimmed = url.trim().toLowerCase();

    // Block dangerous protocols
    const dangerousProtocols = ['javascript:', 'vbscript:', 'data:', 'file:'];
    if (dangerousProtocols.some(protocol => trimmed.startsWith(protocol))) {
        return '';
    }

    // Allow http, https, mailto, tel, and relative URLs
    const safeProtocols = ['http://', 'https://', 'mailto:', 'tel:', '/', '#', '?'];
    if (!safeProtocols.some(protocol => trimmed.startsWith(protocol)) && !trimmed.startsWith('.')) {
        // Prepend https:// if no protocol
        if (!trimmed.includes('://')) {
            return `https://${url.trim()}`;
        }
        return '';
    }

    return url.trim();
}

/**
 * Sanitize filename to prevent path traversal and special characters
 */
export function sanitizeFilename(filename: string | null | undefined): string {
    if (!filename || typeof filename !== 'string') {
        return '';
    }

    // Remove path traversal attempts
    let sanitized = filename
        .replace(/\.\./g, '')
        .replace(/[\/\\]/g, '')
        .replace(/[\x00-\x1f\x80-\x9f]/g, ''); // Remove control characters

    // Keep only safe characters
    sanitized = sanitized.replace(/[^a-zA-Z0-9._-]/g, '_');

    // Prevent hidden files
    if (sanitized.startsWith('.')) {
        sanitized = '_' + sanitized.slice(1);
    }

    // Limit length
    if (sanitized.length > 255) {
        const ext = sanitized.slice(sanitized.lastIndexOf('.'));
        sanitized = sanitized.slice(0, 255 - ext.length) + ext;
    }

    return sanitized || 'file';
}

/**
 * Sanitize object keys and string values recursively
 * Useful for API response sanitization
 */
export function sanitizeObject<T extends object>(obj: T): T {
    if (typeof obj !== 'object' || obj === null) {
        return obj;
    }

    if (Array.isArray(obj)) {
        return obj.map(item => {
            if (typeof item === 'string') {
                return sanitizeText(item);
            }
            if (typeof item === 'object' && item !== null) {
                return sanitizeObject(item);
            }
            return item;
        }) as unknown as T;
    }

    const sanitized: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
        const sanitizedKey = sanitizeText(key);
        if (typeof value === 'string') {
            sanitized[sanitizedKey] = sanitizeText(value);
        } else if (typeof value === 'object' && value !== null) {
            sanitized[sanitizedKey] = sanitizeObject(value as object);
        } else {
            sanitized[sanitizedKey] = value;
        }
    }

    return sanitized as T;
}

/**
 * Create a sanitized text component (React-friendly)
 * Usage: <span>{sanitize.text(userInput)}</span>
 */
export const sanitize = {
    text: sanitizeText,
    html: sanitizeHtml,
    url: sanitizeUrl,
    filename: sanitizeFilename,
    object: sanitizeObject,
    escape: escapeHtml,
};

export default sanitize;
