export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type DexType = "univ2" | "univ3" | "curve" | "balancer";

export type RouteLeg = {
  dex: DexType;
  venue: string;
  token_in: string;
  token_out: string;
  amount_in: string;
  min_out: string;
  data?: string;
};

export type Opportunity = {
  id: string;
  chain: string;
  strategy: string;
  expected_profit_raw: string;
  expected_profit_usd: string;
  route: { legs: RouteLeg[] };
  min_outs: string[];
  can_execute: boolean;
  created_at_ms: number;
  meta: Record<string, JsonValue>;
};

export type Metrics = {
  flashLoans: number;
  attempted: number;
  succeeded: number;
  failed: number;
  last_block: number;
  scan_ms: number;
  last_error: string;
  last_submitted_block: number;
  gas_mode: string;
  send_mode: string;
  realized_profit_raw: string;
  efficiency_pct: number;
  success_rate_pct: number;
};

export type RuntimeState = {
  chain: string;
  opportunities: Opportunity[];
  metrics: Metrics;
  rpc: Record<string, JsonValue>;
};
