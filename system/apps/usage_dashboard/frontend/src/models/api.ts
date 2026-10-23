/**
 * The Usage app's API (system/apps/usage_dashboard/src/usage_dashboard/server.py): the usage collector's answers,
 * passed through, plus the registry's app display names.
 */

import { HttpError, requestJson } from "@imbue/workspace-ui/src/models/http";

/** A totals group's or a call's dimension values; null for "not known". */
export type Group = Record<string, string | null>;

export interface TotalsRow {
  group: Group;
  bucket_start: string | null;
  calls: number;
  unknown_cost_calls: number;
  /** Dollars as a decimal string; null when no call in the group had a known cost. */
  cost_usd: string | null;
  tokens: Record<TokenBucket, number>;
}

export const TOKEN_BUCKETS = ["input", "output", "cache_read", "cache_write"] as const;
export type TokenBucket = (typeof TOKEN_BUCKETS)[number];

export interface LatencyRow {
  group: Group;
  timed_calls: number;
  untimed_calls: number;
  approximate_calls: number;
  p50_ms: number | null;
  p95_ms: number | null;
}

/** One stored model_call event, as the collector keeps it. */
export interface ModelCall {
  event_id: string;
  started_at: string;
  ended_at: string;
  provider: string;
  model: string | null;
  tokens: Partial<Record<TokenBucket | "cache_write_1h", number | null>>;
  cost_usd: string | null;
  cost_provenance: "REPORTED" | "ESTIMATED" | null;
  billing_mode: BillingMode;
  status: string;
  attribution: Group & { origin_kind: string };
}

export type BillingMode = "API_KEY" | "IMBUE_KEY" | "SUBSCRIPTION" | "UNKNOWN";

export interface StoredCall {
  sequence: number;
  event: ModelCall;
}

/** The freshest reading of one subscription window (the collector's ``/v1/limits``). */
export interface LimitReading {
  source: string;
  window: string;
  label: string | null;
  used_percentage: number | null;
  resets_at: string | null;
  window_seconds: number | null;
  observed_at: string;
}

export async function fetchLimits(since: Date): Promise<LimitReading[]> {
  const params = new URLSearchParams({ since: since.toISOString() });
  const answer = await requestJson<{ limits: LimitReading[] }>("GET", `/api/usage/limits?${params}`);
  return answer.limits;
}

export interface CollectorHealth {
  status: string;
  catching_up: boolean;
}

export interface TotalsQuery {
  groupBy: readonly string[];
  since: Date;
  until?: Date;
  bucket?: "minute" | "hour";
}

function totalsParams(query: TotalsQuery): URLSearchParams {
  const params = new URLSearchParams({ group_by: query.groupBy.join(","), since: query.since.toISOString() });
  if (query.until !== undefined) params.set("until", query.until.toISOString());
  if (query.bucket !== undefined) params.set("bucket", query.bucket);
  return params;
}

export async function fetchTotals(query: TotalsQuery): Promise<TotalsRow[]> {
  const answer = await requestJson<{ rows: TotalsRow[] }>("GET", `/api/usage/totals?${totalsParams(query)}`);
  return answer.rows;
}

/** Latency grouped by ``groupBy``, over only the calls whose field is one of ``filters``' values ("" for not known). */
export async function fetchLatency(
  groupBy: readonly string[],
  since: Date,
  filters: Record<string, readonly string[]> = {},
): Promise<LatencyRow[]> {
  const params = new URLSearchParams({ group_by: groupBy.join(","), since: since.toISOString() });
  for (const [field, values] of Object.entries(filters)) params.set(field, values.join(","));
  const answer = await requestJson<{ rows: LatencyRow[] }>("GET", `/api/usage/latency?${params}`);
  return answer.rows;
}

export interface CallsQuery {
  /** Keep calls whose field is one of the given values ("" for not known). */
  filters: Record<string, readonly string[]>;
  limit: number;
  before?: string;
  after?: number;
}

export async function fetchCalls(query: CallsQuery): Promise<StoredCall[]> {
  const params = new URLSearchParams({ limit: String(query.limit) });
  for (const [field, values] of Object.entries(query.filters)) params.set(field, values.join(","));
  if (query.before !== undefined) params.set("before", query.before);
  if (query.after !== undefined) params.set("after", String(query.after));
  const answer = await requestJson<{ calls: StoredCall[] }>("GET", `/api/usage/calls?${params}`);
  return answer.calls;
}

export function fetchCollectorHealth(): Promise<CollectorHealth> {
  return requestJson<CollectorHealth>("GET", "/api/usage/health");
}

export async function fetchAppNames(): Promise<Record<string, string>> {
  const answer = await requestJson<{ display_names: Record<string, string> }>("GET", "/api/apps");
  return answer.display_names;
}

/** Whether a refusal says the collector is down (the app answers 503), not that the request was wrong. */
export function isUnreachable(error: unknown): boolean {
  return error instanceof HttpError && error.status >= 502 && error.status <= 504;
}
