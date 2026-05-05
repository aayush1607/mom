"use client";

import { use } from "react";

import { CartConfirm } from "@/components/CartConfirm";
import { GiveUp } from "@/components/GiveUp";
import { Pakka } from "@/components/Pakka";
import { Phone } from "@/components/Phone";
import { Suggestion } from "@/components/Suggestion";
import { Spinner } from "@/components/ui/Spinner";
import { useRun } from "@/lib/useRun";
import type { AgentError } from "@/types/agent";

interface RunPageProps {
  params: Promise<{ runId: string }>;
}

export default function RunPage({ params }: RunPageProps) {
  const { runId } = use(params);
  const { snapshot, error, isLoading, mutate } = useRun(runId);

  if (isLoading || !snapshot) {
    return (
      <Phone label="run">
        <Spinner label="mom is thinking…" />
      </Phone>
    );
  }

  if (error) {
    return (
      <Phone label="run">
        <div className="px-6 pt-16 text-rose text-[14px]">
          Couldn&apos;t reach mom: {error.message}
        </div>
      </Phone>
    );
  }

  const status = snapshot.status;
  const state = snapshot.state ?? {};
  const proposal = state.proposal ?? null;
  const cart = state.cart ?? null;
  const order = state.order ?? null;
  const agentError = (state.error as AgentError | null | undefined) ?? null;

  return (
    <Phone label={status}>
      {status === "running" ? (
        <Spinner label="mom is picking…" />
      ) : status === "awaiting_proposal" && proposal ? (
        <Suggestion runId={runId} proposal={proposal} onAfterAction={mutate} />
      ) : status === "awaiting_confirm" && cart ? (
        <CartConfirm runId={runId} cart={cart} onAfterAction={mutate} />
      ) : status === "placed" && order ? (
        <Pakka order={order} />
      ) : status === "failed" ? (
        <GiveUp error={agentError} status="failed" />
      ) : status === "cancelled_by_user" ? (
        <GiveUp error={agentError} status="cancelled_by_user" />
      ) : (
        <Spinner label="mom is thinking…" />
      )}
    </Phone>
  );
}
