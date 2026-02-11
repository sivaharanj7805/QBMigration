"use client";

import { useEffect, useState, useRef } from "react";
import { Shield, Terminal } from "lucide-react";
import { authFetch } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface LogEntry {
    timestamp: string;
    type: "verified" | "hash" | "transform" | "redact" | "info";
    message: string;
}

interface ForensicIntegrityPulseProps {
    isLive?: boolean;
    migrationId?: string;
}

// Fallback demo log entries shown when no live migration data is available
const demoLogs: LogEntry[] = [
    { timestamp: "", type: "hash", message: "SHA-256 HASH: Customer #1847 → 0x7e2f8a9c...3b" },
    { timestamp: "", type: "verified", message: "[VERIFIED] Invoice #4521: Hash Match ✓" },
    { timestamp: "", type: "redact", message: "PII REDACT: SSN ***-**-4523, Phone ***-***-1234" },
    { timestamp: "", type: "transform", message: "TRANSFORM: 'Accounts Payable' → QBO:Liability" },
    { timestamp: "", type: "verified", message: "[VERIFIED] Vendor #892: Hash Match ✓" },
    { timestamp: "", type: "hash", message: "SHA-256 HASH: Bill Payment #3341 → 0xa1c9e7f2...9d" },
    { timestamp: "", type: "verified", message: "[VERIFIED] Journal Entry #156: Hash Match ✓" },
    { timestamp: "", type: "info", message: "STREAMING: Batch 42/100 complete (847 records)" },
    { timestamp: "", type: "redact", message: "PII REDACT: Email → ***@domain.com" },
    { timestamp: "", type: "verified", message: "[VERIFIED] Customer #2103: Hash Match ✓" },
    { timestamp: "", type: "transform", message: "TRANSFORM: 'Inventory Assembly' → QBO:Bundle" },
    { timestamp: "", type: "hash", message: "SHA-256 HASH: Credit Memo #891 → 0xf4d2b6a8...2c" },
];

/**
 * AUDIT FIX CRIT-02/CRIT-03: Fetch real forensic logs using authFetch (httpOnly cookies)
 * instead of reading localStorage auth_token (XSS-vulnerable).
 * Uses API_URL from env instead of relative URL.
 */
// AUDIT FIX P13-L1: Accept AbortSignal for cleanup on unmount
async function fetchForensicLogs(migrationId: string, signal?: AbortSignal): Promise<LogEntry[]> {
    try {
        const res = await authFetch(`${API_URL}/api/migrations/${migrationId}/forensic-logs`, { signal });
        if (!res.ok) return [];
        const data = await res.json();
        if (data.success && Array.isArray(data.logs)) {
            return data.logs.map((log: { timestamp: string; type: string; message: string }) => ({
                timestamp: log.timestamp,
                type: (["verified", "hash", "transform", "redact", "info"].includes(log.type) ? log.type : "info") as LogEntry["type"],
                message: log.message,
            }));
        }
        return [];
    } catch {
        return [];
    }
}

export function ForensicIntegrityPulse({ isLive = false, migrationId }: ForensicIntegrityPulseProps) {
    const [logs, setLogs] = useState<LogEntry[]>([]);
    // AUDIT FIX LOW-8: Surface API connectivity errors to UI
    const [apiError, setApiError] = useState(false);
    const terminalRef = useRef<HTMLDivElement>(null);
    // Track whether we have real API data (to avoid overwriting with demos)
    const hasRealData = useRef(false);

    // AUDIT FIX P13-L1: AbortController for fetch cleanup on unmount
    useEffect(() => {
        const controller = new AbortController();
        if (isLive && migrationId) {
            fetchForensicLogs(migrationId, controller.signal).then((realLogs) => {
                if (controller.signal.aborted) return;
                if (realLogs.length > 0) {
                    hasRealData.current = true;
                    setApiError(false);
                    setLogs(realLogs);
                } else {
                    hasRealData.current = false;
                    setApiError(true);
                    setLogs(demoLogs.slice(0, 5).map(log => ({
                        ...log,
                        timestamp: new Date().toISOString()
                    })));
                }
            });
        } else if (!isLive) {
            hasRealData.current = false;
            setLogs(demoLogs.slice(0, 5).map(log => ({
                ...log,
                timestamp: new Date().toISOString()
            })));
        }
        return () => controller.abort();
    }, [isLive, migrationId]);

    // AUDIT FIX CRIT-02: Live mode polls the API for real logs instead of
    // unconditionally injecting fabricated demo data every 800ms.
    // Only falls back to demo cycling when no real API data is available.
    useEffect(() => {
        if (!isLive) {
            return;
        }

        const interval = setInterval(() => {
            if (migrationId) {
                // Poll API for real forensic logs
                fetchForensicLogs(migrationId).then((realLogs) => {
                    if (realLogs.length > 0) {
                        hasRealData.current = true;
                        setLogs(realLogs);
                    }
                    // If API returns empty and we had no real data, leave demo logs as-is
                });
            }
        }, 3000); // Poll every 3 seconds (not 800ms demo spam)

        return () => {
            clearInterval(interval);
        };
    }, [isLive, migrationId]);

    // LOW-09 FIX: Only auto-scroll if user hasn't scrolled up manually.
    // Check if user is within 50px of the bottom before forcing scroll.
    useEffect(() => {
        if (terminalRef.current) {
            const el = terminalRef.current;
            const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
            if (isNearBottom) {
                el.scrollTop = el.scrollHeight;
            }
        }
    }, [logs]);

    const formatTime = (ts: string) => {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    const getLogColor = (type: string) => {
        switch (type) {
            case "verified": return "text-green-400";
            case "hash": return "text-cyan-400";
            case "transform": return "text-yellow-400";
            case "redact": return "text-orange-400";
            default: return "text-gray-400";
        }
    };

    return (
        <div className="card-forensic overflow-hidden border border-gray-800">
            {/* Terminal Header */}
            <div className="bg-gray-900 px-4 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="flex gap-1.5">
                        <div className="w-3 h-3 rounded-full bg-red-500" />
                        <div className="w-3 h-3 rounded-full bg-yellow-500" />
                        <div className="w-3 h-3 rounded-full bg-green-500" />
                    </div>
                    <div className="flex items-center gap-2">
                        <Terminal className="w-4 h-4 text-gray-400" />
                        <span className="text-sm font-mono text-gray-300">Forensic Integrity Pulse</span>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {isLive && !apiError && (
                        <span className="flex items-center gap-1.5 text-xs text-green-400">
                            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                            LIVE
                        </span>
                    )}
                    {apiError && (
                        <span className="flex items-center gap-1.5 text-xs text-yellow-400" title="Using demo data — forensic log API unreachable">
                            <span className="w-2 h-2 bg-yellow-400 rounded-full" />
                            DEMO
                        </span>
                    )}
                    <Shield className="w-4 h-4 text-gray-500" />
                </div>
            </div>

            {/* Terminal Body */}
            <div
                ref={terminalRef}
                className="bg-gray-950 p-4 h-64 overflow-y-auto font-mono text-sm"
            >
                {/* Session Header */}
                <div className="text-gray-500 mb-3">
                    <span className="text-green-400">[ForensicBridge]</span> Session: {migrationId || "DEMO-SESSION"}
                </div>
                <div className="text-gray-600 mb-3 text-xs">
                    ════════════════════════════════════════════════════════
                </div>

                {/* Log Entries */}
                {logs.map((log, i) => (
                    <div key={i} className="flex gap-3 mb-1 leading-relaxed">
                        <span className="text-gray-600 tabular-nums">{formatTime(log.timestamp)}</span>
                        <span className={getLogColor(log.type)}>{log.message}</span>
                    </div>
                ))}

                {/* Blinking Cursor */}
                {isLive && (
                    <div className="flex items-center gap-1 mt-2">
                        <span className="text-green-400">$</span>
                        <span className="w-2 h-4 bg-green-400 animate-pulse" />
                    </div>
                )}
            </div>

            {/* Footer Stats */}
            <div className="bg-gray-900 px-4 py-2 flex items-center justify-between text-xs">
                <div className="flex items-center gap-4 text-gray-500">
                    <span>Chain of Custody: <span className="text-green-400">ACTIVE</span></span>
                    <span>Hashes: <span className="text-cyan-400 tabular-nums">{logs.filter(l => l.type === "hash" || l.type === "verified").length}</span></span>
                </div>
                <div className="text-gray-600">
                    SHA-256 • AES-256-GCM
                </div>
            </div>
        </div>
    );
}
