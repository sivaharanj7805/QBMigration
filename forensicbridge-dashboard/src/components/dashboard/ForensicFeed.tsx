"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal, Pause, Play, Download } from "lucide-react";

interface LogEntry {
    timestamp: string;
    type: "success" | "warning" | "error" | "info" | "hash";
    message: string;
    migration_id?: string;
}

interface ForensicFeedProps {
    activities: LogEntry[];
    isLive?: boolean;
    maxHeight?: string;
    title?: string;
}

export function ForensicFeed({
    activities,
    isLive = true,
    maxHeight = "300px",
    title = "Forensic Integrity Log",
}: ForensicFeedProps) {
    const [isPaused, setIsPaused] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom when new entries arrive
    useEffect(() => {
        if (!isPaused && scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [activities, isPaused]);

    const formatTimestamp = (ts: string) => {
        const date = new Date(ts);
        return date.toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
    };

    const getLogIcon = (type: string) => {
        switch (type) {
            case "success":
                return "✓";
            case "warning":
                return "🛡️";
            case "error":
                return "✕";
            case "hash":
                return "🔒";
            default:
                return "⚙️";
        }
    };

    const getLogClass = (type: string) => {
        switch (type) {
            case "success":
                return "log-success";
            case "warning":
                return "log-warning";
            case "error":
                return "log-error";
            case "hash":
                return "log-hash";
            default:
                return "log-info";
        }
    };

    const handleDownloadLogs = () => {
        const logText = activities
            .map((a) => `[${formatTimestamp(a.timestamp)}] ${a.message}`)
            .join("\n");

        const blob = new Blob([logText], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `forensic-log-${new Date().toISOString().split("T")[0]}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <div className="card-forensic overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-[var(--navy-900)] text-white">
                <div className="flex items-center gap-2">
                    <Terminal className="w-4 h-4 text-[var(--forensic-gold)]" />
                    <span className="text-sm font-medium">{title}</span>
                    {isLive && (
                        <span className="flex items-center gap-1 text-xs">
                            <span className={`w-2 h-2 rounded-full ${isPaused ? "bg-gray-500" : "bg-[var(--success)] animate-pulse"}`} />
                            {isPaused ? "Paused" : "Live"}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {isLive && (
                        <button
                            onClick={() => setIsPaused(!isPaused)}
                            className="p-1.5 hover:bg-white/10 rounded transition-colors"
                            title={isPaused ? "Resume" : "Pause"}
                        >
                            {isPaused ? (
                                <Play className="w-4 h-4" />
                            ) : (
                                <Pause className="w-4 h-4" />
                            )}
                        </button>
                    )}
                    <button
                        onClick={handleDownloadLogs}
                        className="p-1.5 hover:bg-white/10 rounded transition-colors"
                        title="Download Logs"
                    >
                        <Download className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Log Content */}
            <div
                ref={scrollRef}
                className="forensic-terminal"
                style={{ maxHeight }}
            >
                {activities.length === 0 ? (
                    <div className="text-gray-500 text-center py-8">
                        <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>No activity yet</p>
                        <p className="text-xs mt-1">Logs will appear here during migration</p>
                    </div>
                ) : (
                    <div className="space-y-1">
                        {activities.map((entry, index) => (
                            <div key={index} className="flex items-start gap-2">
                                <span className="text-gray-500 shrink-0">
                                    [{formatTimestamp(entry.timestamp)}]
                                </span>
                                <span className={getLogClass(entry.type)}>
                                    {getLogIcon(entry.type)}
                                </span>
                                <span className={getLogClass(entry.type)}>
                                    {formatMessage(entry.message)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// Format message with special highlighting
function formatMessage(message: string): React.ReactNode {
    // Highlight SHA-256 hashes
    const hashMatch = message.match(/(0x[a-fA-F0-9]+\.{3}[a-fA-F0-9]*)/);
    if (hashMatch) {
        const parts = message.split(hashMatch[0]);
        return (
            <>
                {parts[0]}
                <code className="text-forensic-gold font-bold">{hashMatch[0]}</code>
                {parts[1]}
            </>
        );
    }

    // Highlight entity names in quotes
    const entityMatch = message.match(/'([^']+)'/);
    if (entityMatch) {
        const parts = message.split(`'${entityMatch[1]}'`);
        return (
            <>
                {parts[0]}
                <span className="text-[var(--bridge-blue)]">&apos;{entityMatch[1]}&apos;</span>
                {parts[1]}
            </>
        );
    }

    // Highlight [REDACTED]
    if (message.includes("[REDACTED]")) {
        const parts = message.split("[REDACTED]");
        return (
            <>
                {parts[0]}
                <span className="text-[var(--forensic-gold)]">[REDACTED]</span>
                {parts[1]}
            </>
        );
    }

    return message;
}
