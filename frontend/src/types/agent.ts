/**
 * Mirrors backend AgentState pieces. We type only what the FE renders;
 * unknown fields are kept as `unknown` so changes upstream don't crash us.
 */

export type AgentStatus =
  | "running"
  | "awaiting_proposal"
  | "awaiting_confirm"
  | "placed"
  | "cancelled_by_user"
  | "failed";

export type FailureReason =
  | "swap_exhausted"
  | "no_candidates"
  | "nothing_orderable"
  | "mcp_error"
  | "address_not_serviceable"
  | "interrupt_timeout"
  | "payment_not_supported";

export type UserDecisionKind =
  | "accept"
  | "swap"
  | "reject"
  | "confirm"
  | "cancel";

export interface DishCandidate {
  restaurant_id: string;
  restaurant_name: string;
  item_id: string;
  name: string;
  description?: string | null;
  price_inr: number;
  veg?: boolean | null;
}

export interface Proposal {
  dish: DishCandidate;
  reason_summary: string;
  voice_heading: string;
  voice_reason: string;
  voice_cta_yes: string;
  voice_cta_swap: string;
}

export interface CartLine {
  name: string;
  qty: number;
  price_inr: number;
}

export interface CartSnapshot {
  lines: CartLine[];
  subtotal_inr: number;
  delivery_fee_inr: number;
  discount_inr: number;
  total_inr: number;
  payment_methods: string[];
  address_label: string;
  cart_hash: string;
}

export interface OrderResult {
  order_id: string;
  placed_at: string;
  eta_min?: number | null;
}

export interface AgentError {
  reason: FailureReason;
  detail?: string | null;
  voice_message?: string | null;
}

export interface AgentStateView {
  status: AgentStatus;
  proposal?: Proposal | null;
  cart?: CartSnapshot | null;
  order?: OrderResult | null;
  error?: AgentError | null;
  swap_count?: number;
  // Plus unknown extras from the backend snapshot.
  [key: string]: unknown;
}

export interface RunSnapshot {
  run_id: string;
  thread_id: string;
  status: AgentStatus;
  state: AgentStateView;
}

export interface CreateRunResponse {
  run_id: string;
  thread_id: string;
  status: AgentStatus;
}

// ── Inputs (POST /agent/runs body) ───────────────────────────────────────────

export interface PersonaInput {
  system_prompt: string;
  voice_pack_id: string;
  name: string;
}

export interface UserContext {
  active_nudge?: string | null;
  meal_slot?: "breakfast" | "lunch" | "snack" | "dinner" | null;
  day_of_week?: string | null;
  local_time?: string | null;
}

export interface Constraints {
  max_price_inr: number;
  max_eta_min: number;
  vegetarian: boolean;
  jain: boolean;
  egg_ok: boolean;
}

export interface AgentRunInput {
  user_id: string;
  address_id: string;
  address_label?: string | null;
  prompt?: string | null;
  context: UserContext;
  constraints: Constraints;
  persona: PersonaInput;
}

export interface CreateRunRequest {
  input: AgentRunInput;
  user_token: string;
}

export interface ResumeRequest {
  decision: UserDecisionKind;
  note?: string | null;
  user_token: string;
}

export const TERMINAL_STATUSES: AgentStatus[] = [
  "placed",
  "cancelled_by_user",
  "failed",
];

export function isTerminal(status: AgentStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export function isAwaitingUser(status: AgentStatus): boolean {
  return status === "awaiting_proposal" || status === "awaiting_confirm";
}
