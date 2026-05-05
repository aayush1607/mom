"use client";

import { useState } from "react";

import { Phone } from "@/components/Phone";
import { Button } from "@/components/ui/Button";
import { useRun } from "@/lib/useRun";

export default function DebugPage() {
  const [runId, setRunId] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const { snapshot, error } = useRun(active);

  return (
    <Phone label="debug">
      <div className="px-6 pt-12 pb-8 space-y-4">
        <h1 className="h-display text-[24px]">Debug</h1>
        <div className="flex gap-2">
          <input
            type="text"
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            placeholder="run_id"
            className="flex-1 bg-card border border-line rounded-xl px-3 py-2 text-[13px] font-mono"
          />
          <Button onClick={() => setActive(runId.trim() || null)}>Load</Button>
        </div>
        {error ? (
          <p className="text-[12px] text-rose">Error: {error.message}</p>
        ) : null}
        {snapshot ? (
          <pre className="text-[11px] leading-tight bg-bg/40 border border-line rounded-2xl p-3 overflow-x-auto whitespace-pre-wrap break-words">
            {JSON.stringify(snapshot, null, 2)}
          </pre>
        ) : null}
      </div>
    </Phone>
  );
}
