const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// Trích thông điệp lỗi dễ hiểu từ phản hồi FastAPI:
//  - HTTPException  → { detail: "..." }
//  - Lỗi validate   → { detail: [{ msg, loc }] }  (vd toạ độ ngoài Việt Nam)
async function errMessage(r: Response, fallback: string): Promise<string> {
  try {
    const d = await r.json();
    if (typeof d?.detail === "string") return d.detail;
    if (Array.isArray(d?.detail) && d.detail[0]?.msg) {
      return d.detail[0].msg.replace(/^Value error,\s*/, "");
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

export type ModuleInfo = {
  id: string;
  name: string;
  group: string;
  status: string;
  icon: string;
  data_sources: string[];
  users: string[];
  description: string;
};

export type ForecastPoint = {
  day: number;
  date: string;
  value: number;
  unit: string;
  risk: string;
};

export type Assessment = {
  module_id: string;
  module_name: string;
  location: { lat: number; lon: number };
  status: string;
  risk_level: string;
  headline: string;
  detail: string;
  recommendation: string;
  confidence?: number;
  confidence_low?: number;
  confidence_high?: number;
  is_real?: boolean;
  score?: number;
  metrics?: Record<string, number>;
  forecast: ForecastPoint[];
  data_sources: string[];
};

export type TerraScore = {
  location: { lat: number; lon: number };
  score: number;
  grade: string;
  summary: string;
  breakdown: Record<string, number>;
  real_data_ratio?: number;
};

export type BacktestEvent = {
  id: string;
  label: string;
  module: string;
  note: string;
};

export type BacktestPoint = {
  date: string;
  value: number;
  precip: number;
  warning?: boolean;
  danger: boolean;
};

export type AlarmRate = {
  windows: number;
  alarms: number;
  alarm_rate_pct: number;
  threshold: number;
};

export type BacktestResult = {
  event_id: string;
  label: string;
  module: string;
  note: string;
  available: boolean;
  message?: string;
  location?: { lat: number; lon: number };
  event_date?: string;
  terrain?: string;
  threshold?: number;
  threshold_warning?: number;
  lead_days?: number | null;
  lead_days_warning?: number | null;
  success?: boolean;
  verdict?: string;
  peak?: BacktestPoint;
  first_danger?: BacktestPoint | null;
  first_warning?: BacktestPoint | null;
  series?: BacktestPoint[];
  alarm_rate?: AlarmRate | null;
  alarm_rate_warning?: AlarmRate | null;
  honesty_note?: string;
  data_source?: string;
};

export type CopilotAnswer = {
  answer: string;
  used_modules: string[];
  llm?: boolean;
};

export async function getModules(): Promise<ModuleInfo[]> {
  const r = await fetch(`${BASE}/api/modules`);
  if (!r.ok) throw new Error("Không tải được danh sách mô-đun");
  return r.json();
}

export async function assess(
  moduleId: string,
  lat: number,
  lon: number,
  areaHa?: number,
): Promise<Assessment> {
  const body: Record<string, number> = { lat, lon };
  if (areaHa != null) body.area_ha = areaHa;
  const r = await fetch(`${BASE}/api/assess/${moduleId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không lấy được đánh giá"));
  return r.json();
}

export async function getTerraScore(lat: number, lon: number): Promise<TerraScore> {
  const r = await fetch(`${BASE}/api/terrascore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon }),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không lấy được TerraScore"));
  return r.json();
}

export async function askCopilot(
  question: string,
  lat: number,
  lon: number,
): Promise<CopilotAnswer> {
  const r = await fetch(`${BASE}/api/copilot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, location: { lat, lon } }),
  });
  if (!r.ok) throw new Error("Không hỏi được trợ lý");
  return r.json();
}

export type ScanModule = {
  id: string;
  name: string;
  icon: string;
  group: string;
  risk_level: string;
  headline: string;
  recommendation: string;
  is_real: boolean;
  score?: number;
};

export type ScanResult = {
  location: { lat: number; lon: number };
  terrascore: TerraScore;
  modules: ScanModule[];
  alerts: ScanModule[];
  real_data_ratio: number;
  generated_at: string;
};

export type ScenarioPoint = {
  day: number;
  date: string;
  value: number;
  risk: string;
};

export type ScenarioResult = {
  label: string;
  rain_mult: number;
  temp_delta: number;
  peak: number;
  first_danger_date?: string | null;
  series: ScenarioPoint[];
};

export type WhatIfResult = {
  module_id: string;
  module_name: string;
  location: { lat: number; lon: number };
  unit: string;
  safe: number;
  warning: number;
  is_real: boolean;
  note: string;
  scenarios: ScenarioResult[];
};

export const WHATIF_MODULES = ["drought", "flood", "wildfire", "landslide"];

export async function scanAll(
  lat: number,
  lon: number,
  areaHa?: number,
): Promise<ScanResult> {
  const body: Record<string, number> = { lat, lon };
  if (areaHa != null) body.area_ha = areaHa;
  const r = await fetch(`${BASE}/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không quét được toàn cảnh"));
  return r.json();
}

export async function runWhatIf(
  moduleId: string,
  lat: number,
  lon: number,
): Promise<WhatIfResult> {
  const r = await fetch(`${BASE}/api/whatif/${moduleId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon }),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không chạy được kịch bản what-if"));
  return r.json();
}

// ---- S07 Causal Explain ----
export type ExplainFactor = {
  factor: string;
  peak_without: number;
  contribution: number;
  share_pct: number;
  note: string;
};

export type ExplainResult = {
  module_id: string;
  module_name: string;
  unit: string;
  available: boolean;
  message?: string;
  peak?: number;
  peak_date?: string | null;
  terrain?: string;
  headline?: string;
  factors: ExplainFactor[];
  wettest_day?: { date: string; precip_mm: number };
  method?: string;
};

// ---- S03 Goal-Seek ----
export type GoalLever = {
  lever: string;
  kind: string;
  feasible: boolean;
  answer: string;
  value: number | null;
};

export type GoalSeekResult = {
  module_id: string;
  module_name: string;
  unit: string;
  available: boolean;
  message?: string;
  current_peak?: number;
  target?: number;
  safe_now?: boolean;
  headline?: string;
  levers: GoalLever[];
  combined?: { answer: string } | null;
  method?: string;
};

// ---- S02 Time Machine ----
export type TimeMachineMember = {
  year: number;
  peak: number;
  rain_total_mm: number;
  danger: boolean;
  warning: boolean;
};

export type TimeMachineResult = {
  module_id: string;
  module_name: string;
  unit: string;
  available: boolean;
  message?: string;
  years?: number;
  from_year?: number;
  to_year?: number;
  prob_danger_pct?: number;
  prob_warning_pct?: number;
  p10?: number;
  p50?: number;
  p90?: number;
  current_peak?: number | null;
  current_rank_pct?: number | null;
  worst_year?: { year: number; peak: number; rain_total_mm: number };
  best_year?: { year: number; peak: number; rain_total_mm: number };
  headline?: string;
  members: TimeMachineMember[];
  threshold_warning?: number;
  method?: string;
};

// ---- C10 Anomaly ----
export type AnomalyMetric = {
  key: string;
  label: string;
  unit: string;
  current: number;
  normal_mean: number;
  normal_std: number;
  z_score: number | null;
  percentile: number;
  level: string;
  verdict: string;
  alert: boolean;
};

export type AnomalyResult = {
  available: boolean;
  message?: string;
  years?: number;
  from_year?: number;
  to_year?: number;
  headline?: string;
  metrics: AnomalyMetric[];
  method?: string;
};

// ---- Tài khoản & thửa đất (thay localStorage) ----
export type AuthUser = { id: number; email: string; name: string };
export type TokenResponse = { access_token: string; user: AuthUser };

export type ServerPlot = {
  id: number;
  name: string;
  lat: number;
  lon: number;
  area_ha: number | null;
  score: number | null;
  grade: string | null;
  created_at: string;
};

const TOKEN_KEY = "terratwin_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function authed<T>(
  path: string,
  init: RequestInit,
  err: string,
): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init.headers as Record<string, string> | undefined),
    },
  });
  if (r.status === 401) {
    setToken(null);
    throw new Error("Phiên đăng nhập đã hết hạn — vui lòng đăng nhập lại.");
  }
  if (!r.ok) throw new Error(await errMessage(r, err));
  return r.status === 204 ? (undefined as T) : r.json();
}

export function register(email: string, password: string, name: string) {
  return authed<TokenResponse>("/api/auth/register",
    { method: "POST", body: JSON.stringify({ email, password, name }) },
    "Không đăng ký được");
}

export function login(email: string, password: string) {
  return authed<TokenResponse>("/api/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) },
    "Không đăng nhập được");
}

export function fetchMe() {
  return authed<AuthUser>("/api/auth/me", { method: "GET" }, "Không lấy được tài khoản");
}

export function listPlots() {
  return authed<ServerPlot[]>("/api/plots", { method: "GET" },
    "Không tải được danh mục thửa đất");
}

export function savePlot(
  name: string,
  lat: number,
  lon: number,
  areaHa?: number,
  score?: number,
  grade?: string,
) {
  const location: Record<string, number> = { lat, lon };
  if (areaHa != null) location.area_ha = areaHa;
  return authed<ServerPlot>("/api/plots",
    { method: "POST", body: JSON.stringify({ name, location, score, grade }) },
    "Không lưu được thửa đất");
}

export function deletePlot(id: number) {
  return authed<void>(`/api/plots/${id}`, { method: "DELETE" },
    "Không xóa được thửa đất");
}

// ---- C06 Heatmap ----
export type HeatCell = {
  lat: number;
  lon: number;
  value: number | null;
  risk: string;
};

export type HeatmapResult = {
  module_id: string;
  module_name: string;
  unit: string;
  center: { lat: number; lon: number };
  radius_km: number;
  side: number;
  cells: HeatCell[];
  cell_dlat: number;
  cell_dlon: number;
  calibrated: boolean;
  safe: number;
  warning: number;
  n_danger: number;
  n_warning: number;
  hottest: HeatCell | null;
  headline: string;
  cached: boolean;
  caveat: string;
  method: string;
};

export function runHeatmap(
  moduleId: string,
  lat: number,
  lon: number,
  side = 7,
  radiusKm = 8,
) {
  return postJson<HeatmapResult>(
    `/api/heatmap/${moduleId}?side=${side}&radius_km=${radiusKm}`,
    { lat, lon },
    "Không dựng được bản đồ nhiệt",
  );
}

// ---- C03 / C09 hỏi bằng lời ----
export type AskResult = {
  understood: boolean;
  available?: boolean;
  question: string;
  message?: string;
  module_id?: string;
  module_name?: string;
  unit?: string;
  rain_mult?: number;
  temp_delta?: number;
  parsed_by?: string;
  baseline_peak?: number;
  scenario_peak?: number;
  delta?: number;
  risk_level?: string;
  headline?: string;
  method?: string;
  llm_available?: boolean;
};

export function runAsk(
  question: string,
  lat: number,
  lon: number,
  moduleId = "flood",
) {
  return postJson<AskResult>("/api/ask",
    { question, location: { lat, lon }, module_id: moduleId },
    "Không hỏi được");
}

// ---- C05 Proactive Radar ----
export type AlertRow = {
  id: number;
  plot_id: number | null;
  module_id: string;
  risk_level: string;
  headline: string;
  recommendation: string;
  created_at: string;
  acknowledged: boolean;
};

export type RadarRun = {
  plots_scanned: number;
  new_alerts: number;
  dedup_window_hours?: number;
  message?: string;
};

export function runRadar() {
  return authed<RadarRun>("/api/radar/run", { method: "POST" },
    "Không chạy được rà soát");
}

export function listAlerts(unreadOnly = false) {
  return authed<AlertRow[]>(`/api/alerts?unread_only=${unreadOnly}`,
    { method: "GET" }, "Không tải được cảnh báo");
}

export function ackAlert(id: number) {
  return authed<AlertRow>(`/api/alerts/${id}/ack`, { method: "POST" },
    "Không đánh dấu được");
}

async function postJson<T>(path: string, body: unknown, err: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, err));
  return r.json();
}

export function runExplain(moduleId: string, lat: number, lon: number) {
  return postJson<ExplainResult>(`/api/explain/${moduleId}`, { lat, lon },
    "Không phân tích được nguyên nhân");
}

export function runGoalSeek(moduleId: string, lat: number, lon: number) {
  return postJson<GoalSeekResult>(`/api/goalseek/${moduleId}`, { lat, lon },
    "Không chạy được mô phỏng ngược");
}

export function runTimeMachine(moduleId: string, lat: number, lon: number) {
  return postJson<TimeMachineResult>(`/api/timemachine/${moduleId}`, { lat, lon },
    "Không chạy được cỗ máy thời gian");
}

export function runAnomaly(lat: number, lon: number) {
  return postJson<AnomalyResult>("/api/anomaly", { lat, lon },
    "Không so sánh được với khí hậu nền");
}

export async function getBacktests(): Promise<BacktestEvent[]> {
  const r = await fetch(`${BASE}/api/backtest`);
  if (!r.ok) throw new Error("Không tải được danh sách backtest");
  return r.json();
}

export async function runBacktest(eventId: string): Promise<BacktestResult> {
  const r = await fetch(`${BASE}/api/backtest/${eventId}`);
  if (!r.ok) throw new Error("Không chạy được backtest");
  return r.json();
}
