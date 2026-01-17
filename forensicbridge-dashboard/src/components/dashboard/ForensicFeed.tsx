"use client";

import { Shield, Database, Upload, CheckCircle2, Clock, AlertTriangle, Info } from "lucide-react";

interface FeedEvent {
    id?: string;
    type: "extraction" | "upload" | "verification" | "hash" | "complete" | "success" | "warning" | "info" | "error";
    message: string;
    timestamp: string;
    details?: string;
}

interface ForensicFeedProps {
    events?: FeedEvent[];
    activities?: FeedEvent[]; // Alternate prop name
    isLive?: boolean;
    title?: string;
}

const eventIcons = {
    extraction: Database,
    upload: Upload,
    verification: Shield,
    hash: Shield,
    complete: CheckCircle2,
    success: CheckCircle2,
    warning: AlertTriangle,
    info: Info,
    error: AlertTriangle
};

const eventColors = {
    extraction: "bg-blue-100 text-blue-600",
    upload: "bg-purple-100 text-purple-600",
    verification: "bg-yellow-100 text-yellow-600",
    hash: "bg-green-100 text-green-600",
    complete: "bg-green-100 text-green-600",
    success: "bg-green-100 text-green-600",
    warning: "bg-yellow-100 text-yellow-600",
    info: "bg-blue-100 text-blue-600",
    error: "bg-red-100 text-red-600"
};

export function ForensicFeed({ events, activities, isLive = false, title = "Forensic Activity Log" }: ForensicFeedProps) {
    // Support both events and activities prop names
    const feedItems = events || activities || [];

    const formatTimestamp = (ts: string) => {
        const date = new Date(ts);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    return (
        <div className="card-forensic">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">{title}</h3>
                {isLive && (
                    <span className="flex items-center gap-1.5 text-xs text-green-600">
                        <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                        Live
                    </span>
                )}
            </div>

            <div className="max-h-[300px] overflow-y-auto">
                {feedItems.length === 0 ? (
                    <div className="p-8 text-center text-gray-400">
                        <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>No activity yet</p>
                    </div>
                ) : (
                    <div className="divide-y divide-gray-50">
                        {feedItems.map((event, index) => {
                            const Icon = eventIcons[event.type] || Info;
                            const colorClass = eventColors[event.type] || "bg-gray-100 text-gray-600";

                            return (
                                <div key={event.id || index} className="px-4 py-3 flex items-start gap-3">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                                        <Icon className="w-4 h-4" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-gray-900">{event.message}</p>
                                        {event.details && (
                                            <p className="text-xs text-gray-500 mt-0.5 truncate">{event.details}</p>
                                        )}
                                    </div>
                                    <span className="text-xs text-gray-400 flex-shrink-0 tabular-nums">
                                        {formatTimestamp(event.timestamp)}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
