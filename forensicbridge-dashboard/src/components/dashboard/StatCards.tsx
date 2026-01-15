"use client";

import { TrendingUp, TrendingDown, Users, Clock, CheckCircle, AlertCircle, Activity, Database } from "lucide-react";

interface StatCardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    icon: React.ReactNode;
    color?: "blue" | "green" | "gold" | "red" | "gray";
}

function StatCard({ title, value, subtitle, trend, icon, color = "blue" }: StatCardProps) {
    const colorClasses = {
        blue: "text-[var(--bridge-blue)]",
        green: "text-[var(--success)]",
        gold: "text-[var(--forensic-gold)]",
        red: "text-[var(--error)]",
        gray: "text-gray-500",
    };

    return (
        <div className="stat-card">
            <div className="flex items-start justify-between">
                <div>
                    <p className="stat-label">{title}</p>
                    <p className="stat-value mt-1">{value}</p>
                    {subtitle && (
                        <p className="text-xs text-gray-500 mt-1">{subtitle}</p>
                    )}
                </div>
                <div className={`p-2 rounded-lg bg-gray-50 ${colorClasses[color]}`}>
                    {icon}
                </div>
            </div>
            {trend && (
                <div className={`flex items-center gap-1 mt-3 text-sm ${trend.isPositive ? "text-[var(--success)]" : "text-[var(--error)]"}`}>
                    {trend.isPositive ? (
                        <TrendingUp className="w-4 h-4" />
                    ) : (
                        <TrendingDown className="w-4 h-4" />
                    )}
                    <span>{Math.abs(trend.value)}% vs last week</span>
                </div>
            )}
        </div>
    );
}

interface DashboardOverview {
    total_migrations: number;
    completed_migrations: number;
    failed_migrations: number;
    in_progress: number;
    success_rate: number;
    avg_duration_minutes: number;
    recent_completed_24h: number;
}

interface StatCardsProps {
    overview: DashboardOverview | null;
    isLoading?: boolean;
}

export function StatCards({ overview, isLoading }: StatCardsProps) {
    if (isLoading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="stat-card animate-pulse">
                        <div className="h-4 bg-gray-200 rounded w-24 mb-2" />
                        <div className="h-8 bg-gray-200 rounded w-16" />
                    </div>
                ))}
            </div>
        );
    }

    if (!overview) {
        return null;
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
                title="Total Migrations"
                value={overview.total_migrations}
                subtitle={`${overview.in_progress} in progress`}
                icon={<Database className="w-5 h-5" />}
                color="blue"
            />
            <StatCard
                title="Completed"
                value={overview.completed_migrations}
                subtitle={`${overview.recent_completed_24h} in last 24h`}
                icon={<CheckCircle className="w-5 h-5" />}
                color="green"
                trend={{ value: 12, isPositive: true }}
            />
            <StatCard
                title="Success Rate"
                value={`${overview.success_rate}%`}
                subtitle="Forensic verified"
                icon={<Activity className="w-5 h-5" />}
                color="gold"
            />
            <StatCard
                title="Avg Duration"
                value={`${overview.avg_duration_minutes} min`}
                subtitle="Per migration"
                icon={<Clock className="w-5 h-5" />}
                color="gray"
            />
        </div>
    );
}

// Individual exports for flexibility
export { StatCard };
