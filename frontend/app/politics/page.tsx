"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export default function PoliticsPage() {
  const [disclosures, setDisclosures] = useState<unknown[]>([]);

  useEffect(() => {
    fetch(`${API}/politics/disclosures`).then(r => r.json()).then(d => setDisclosures(d.disclosures || []));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Presidential Trade Tracker</h1>
        <p className="text-gray-400 text-sm mt-1">
          OGE public disclosures — fully legal. Cross-references official stock purchases vs subsequent govt contracts/deals.
        </p>
      </div>

      <div className="space-y-3">
        {disclosures.length === 0 ? (
          <div className="text-center py-16 text-gray-500">Loading OGE disclosures...</div>
        ) : disclosures.map((d: unknown, i) => {
          const disc = d as {
            official_name: string; symbol: string; transaction_type: string;
            amount_range: string; transaction_date: string; subsequent_govt_event?: string;
            official_role: string;
          };
          return (
            <div key={i} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="flex items-start gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-white font-bold">{disc.official_name}</span>
                    <span className="text-gray-500 text-xs">{disc.official_role}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      disc.transaction_type === "purchase" ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"
                    }`}>{disc.transaction_type}</span>
                  </div>
                  <div className="text-gray-300 text-sm">
                    <Link href={`/analysis/${disc.symbol}`} className="text-blue-400 hover:underline font-bold mr-2">{disc.symbol}</Link>
                    {disc.amount_range} · {disc.transaction_date}
                  </div>
                  {disc.subsequent_govt_event && (
                    <div className="mt-2 bg-yellow-900/20 border border-yellow-800/50 rounded p-2 text-yellow-300 text-xs">
                      📋 Subsequent: {disc.subsequent_govt_event}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
