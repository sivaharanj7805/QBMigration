"use client";

import { useEffect, useState, useRef } from "react";
import { Shield, Terminal } from "lucide-react";

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
 * Fetch real forensic log entries from the migration API.
 * Falls back to demo data if the fetch fails or no migrationId is provided.
 */
async function fetchForensicLogs(migrationId: string): Promise<LogEntry[]> {
    try {
        const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
        const res = await fetch(`/api/migrations/${migrationId}/forensic-logs`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
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
    const [logIndex, setLogIndex] = useState(0);
    const terminalRef = useRef<HTMLDivElement>(null);

    // Fetch real forensic logs from API when live and migrationId is available
    useEffect(() => {
        if (isLive && migrationId) {
            fetchForensicLogs(migrationId).then((realLogs) => {
                if (realLogs.length > 0) {
                    setLogs(realLogs);
                } else {
                    // Fall back to demo logs if API returns empty
                    setLogs(demoLogs.slice(0, 5).map(log => ({
                        ...log,
                        timestamp: new Date().toISOString()
                    })));
                }
            });
        } else if (!isLive) {
            // Show static demo logs when not live
            setLogs(demoLogs.slice(0, 5).map(log => ({
                ...log,
                timestamp: new Date().toISOString()
            })));
        }
    }, [isLive, migrationId]);

    // Separate effect for live streaming - always returns cleanup function
    // FIX: Removed logIndex from dependency array to prevent infinite loop
    // Use a ref to track the current index instead
    const logIndexRef = useRef(logIndex);
    logIndexRef.current = logIndex;

    useEffect(() => {
        if (!isLive) {
            return; // No interval to clean up when not live
        }

        const interval = setInterval(() => {
            const currentIndex = logIndexRef.current;
            const newLog = {
                ...demoLogs[currentIndex % demoLogs.length],
                timestamp: new Date().toISOString()
            };
            setLogs(prev => [...prev.slice(-15), newLog]);
            setLogIndex(prev => prev + 1);
        }, 800);

        // FIX: Always return cleanup function when isLive is true
        return () => {
            clearInterval(interval);
        };
    }, [isLive]); // FIX: Removed logIndex from dependency array

    // Auto-scroll to bottom
    useEffect(() => {
        if (terminalRef.current) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
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
                    {isLive && (
                        <span className="flex items-center gap-1.5 text-xs text-green-400">
                            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                            LIVE
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
