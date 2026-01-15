"use client";

import { useDashboardOverview, useRecentActivity } from "@/lib/hooks/useDashboard";
import { useBulkStatus } from "@/lib/hooks/useMigrations";
import { StatCards } from "@/components/dashboard/StatCards";
import { ForensicFeed } from "@/components/dashboard/ForensicFeed";
import { PizzaTracker } from "@/components/dashboard/PizzaTracker";
import { ReconciliationShield } from "@/components/dashboard/ReconciliationShield";
import { MigrationsTable } from "@/components/migrations/MigrationsTable";
import { Loader2, TrendingUp, Shield, Zap } from "lucide-react";
import Link from "next/link";

export default function DashboardPage() {
  const { data: overview, isLoading: overviewLoading } = useDashboardOverview();
  const { data: activities, isLoading: activitiesLoading } = useRecentActivity();
  const { data: bulkData, isLoading: migrationsLoading } = useBulkStatus();

  // Get active migration if any
  const migrations = bulkData?.migrations ? Object.values(bulkData.migrations) : [];
  const activeMigration = migrations.find(
    (m) => m.status === "processing" || m.status === "provisioning"
  );

  // Mock phases for demo (in production, this comes from useLiveStatus)
  const demoPhases = [
    { name: "EXTRACTION", status: "completed" as const, percentage: 100, description: "Decrypting and hashing records" },
    { name: "TRANSIT", status: "completed" as const, percentage: 100, description: "Uploading to secure cloud" },
    { name: "TRANSFORMATION", status: "in_progress" as const, percentage: 65, description: "Reconstructing linked transactions" },
    { name: "VERIFICATION", status: "pending" as const, percentage: 0, description: "Validating trial balance" },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Migration Command Center</h1>
          <p className="text-sm text-gray-500 mt-1">
            Real-time monitoring of all active migrations
          </p>
        </div>
        <Link
          href="/migrations"
          className="flex items-center gap-2 px-4 py-2 bg-[var(--bridge-blue)] text-white text-sm font-medium rounded-lg hover:bg-[var(--bridge-blue)]/90 transition-colors"
        >
          <Zap className="w-4 h-4" />
          New Migration
        </Link>
      </div>

      {/* Stats Overview */}
      <StatCards overview={overview || null} isLoading={overviewLoading} />

      {/* Active Migration Tracker (if any) */}
      {activeMigration ? (
        <PizzaTracker
          phases={demoPhases}
          currentPhase={3}
          overallPercentage={activeMigration.progress_percent}
          currentEntity={activeMigration.current_step}
          statusMessage={`Processing ${activeMigration.company_name}...`}
          companyName={activeMigration.company_name}
          elapsedSeconds={
            (Date.now() - new Date(activeMigration.created_at).getTime()) / 1000
          }
        />
      ) : (
        <div className="card-forensic p-8 text-center">
          <Shield className="w-12 h-12 mx-auto text-gray-300 mb-3" />
          <h3 className="text-lg font-medium text-gray-700">No Active Migrations</h3>
          <p className="text-sm text-gray-500 mt-1">
            Start a new migration from the Migrations tab or wait for a client upload.
          </p>
        </div>
      )}

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Reconciliation Shield Demo */}
        <ReconciliationShield
          sourceBalance={1450220.1}
          destinationBalance={1450220.1}
          discrepancy={0}
          isBalanced={true}
          forensicStatus="VERIFIED"
          verificationTimestamp={new Date().toISOString()}
          sourceHash="0x7e2f8a9c3b..."
          destinationHash="0x7e2f8a9c3b..."
          hashMatch={true}
          migrationId="FB-2026-X99"
        />

        {/* Forensic Feed */}
        <ForensicFeed
          activities={
            activities?.map((a) => ({
              timestamp: a.timestamp,
              type: a.type as "success" | "warning" | "error" | "info" | "hash",
              message: a.message,
              migration_id: a.migration_id,
            })) || []
          }
          isLive={true}
          title="Chain of Custody Log"
        />
      </div>

      {/* Recent Migrations Table */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Migrations</h2>
          <Link
            href="/migrations"
            className="text-sm text-[var(--bridge-blue)] hover:underline"
          >
            View All →
          </Link>
        </div>
        <MigrationsTable
          migrations={migrations.slice(0, 5)}
          isLoading={migrationsLoading}
        />
      </div>
    </div>
  );
}
