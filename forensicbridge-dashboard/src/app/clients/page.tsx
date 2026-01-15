"use client";

import { Users, Plus, Search, MoreHorizontal, Building2, Phone, Mail } from "lucide-react";
import { useState } from "react";

// Demo data
const demoClients = [
    {
        id: "cli_001",
        name: "Waterloo Manufacturing",
        contact: "John Smith",
        email: "john@waterloocorp.com",
        phone: "(555) 123-4567",
        migrations_count: 3,
        last_migration: "2026-01-14",
        status: "active",
    },
    {
        id: "cli_002",
        name: "Smith & Associates CPA",
        contact: "Mary Johnson",
        email: "mjohnson@smithcpa.com",
        phone: "(555) 987-6543",
        migrations_count: 12,
        last_migration: "2026-01-13",
        status: "active",
    },
    {
        id: "cli_003",
        name: "TechCorp Industries",
        contact: "Robert Chen",
        email: "rchen@techcorp.io",
        phone: "(555) 456-7890",
        migrations_count: 1,
        last_migration: "2026-01-10",
        status: "pending",
    },
];

export default function ClientsPage() {
    const [searchQuery, setSearchQuery] = useState("");

    const filteredClients = demoClients.filter(
        (c) =>
            c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.contact.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.email.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="space-y-6">
            {/* Page Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">CPA Client Library</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        Manage your client directory and track migration history
                    </p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 bg-[var(--bridge-blue)] text-white text-sm font-medium rounded-lg hover:bg-[var(--bridge-blue)]/90 transition-colors">
                    <Plus className="w-4 h-4" />
                    Add Client
                </button>
            </div>

            {/* Search */}
            <div className="card-forensic p-4">
                <div className="relative max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search clients..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 text-sm border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)] focus:border-transparent"
                    />
                </div>
            </div>

            {/* Clients Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredClients.map((client) => (
                    <div key={client.id} className="card-forensic p-5 hover:shadow-lg transition-shadow">
                        <div className="flex items-start justify-between mb-4">
                            <div className="w-12 h-12 bg-gradient-to-br from-[var(--bridge-blue)] to-[var(--navy-800)] rounded-lg flex items-center justify-center">
                                <Building2 className="w-6 h-6 text-white" />
                            </div>
                            <button className="p-1.5 hover:bg-gray-100 rounded transition-colors">
                                <MoreHorizontal className="w-4 h-4 text-gray-400" />
                            </button>
                        </div>

                        <h3 className="font-semibold text-gray-900">{client.name}</h3>
                        <p className="text-sm text-gray-500 mt-1">{client.contact}</p>

                        <div className="mt-4 space-y-2">
                            <div className="flex items-center gap-2 text-sm text-gray-600">
                                <Mail className="w-4 h-4 text-gray-400" />
                                {client.email}
                            </div>
                            <div className="flex items-center gap-2 text-sm text-gray-600">
                                <Phone className="w-4 h-4 text-gray-400" />
                                {client.phone}
                            </div>
                        </div>

                        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
                            <div>
                                <p className="text-xs text-gray-500">Migrations</p>
                                <p className="font-bold text-lg">{client.migrations_count}</p>
                            </div>
                            <div className="text-right">
                                <p className="text-xs text-gray-500">Last Active</p>
                                <p className="text-sm font-medium text-gray-700">{client.last_migration}</p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {filteredClients.length === 0 && (
                <div className="text-center py-12 text-gray-500">
                    <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
                    <p>No clients found</p>
                </div>
            )}
        </div>
    );
}
