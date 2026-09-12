const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// N6 — đếm sự kiện ẨN DANH. Fire-and-forget: không await, không chặn UI, nuốt
// mọi lỗi (đo lường KHÔNG bao giờ được làm hỏng luồng chính), không gửi gì định
// danh. Backend chỉ nhận sáu tên hợp lệ; tên lạ bị bỏ qua.
export function trackEvent(name: string, meta?: Record<string, unknown>) {
  try {
    void fetch(`${BASE}/api/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, meta }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* im lặng */
  }
}

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
  region?: RegionInfo;
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

export type KnowledgeCitation = {
  id: number;
  title: string;
  author_name: string;
  similarity_pct: number;
  distance_km: number;
};
export type CopilotAnswer = {
  answer: string;
  used_modules: string[];
  llm?: boolean;
  knowledge_used?: KnowledgeCitation[];
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
  // "ok" | "need_data" | "out_of_scope" | "pending"
  status?: string;
  confidence?: number | null;
  name: string;
  icon: string;
  group: string;
  risk_level: string;
  headline: string;
  recommendation: string;
  is_real: boolean;
  score?: number;
  spark?: number[];
  unit?: string | null;
  peak?: number | null;
};

export type RegionInfo = {
  kind: "land" | "sea" | "foreign" | "unknown";
  serviceable: boolean;
  elevation_m?: number | null;
  land_neighbours?: number | null;
  country?: string | null;
  in_vietnam?: boolean | null;
  note?: string | null;
  caveat?: string | null;
};

export type ScanResult = {
  location: { lat: number; lon: number };
  region?: RegionInfo;
  terrascore: TerraScore;
  modules: ScanModule[];
  alerts: ScanModule[];
  real_data_ratio: number;
  generated_at: string;
  // Mô-đun "nặng" (quét cả một vùng) bị bỏ qua trong lượt toàn cảnh — khai báo
  // ra chứ không giấu, để người dùng biết còn thứ gì cần mở riêng.
  skipped_heavy?: string[];
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
  deep = false,
): Promise<ScanResult> {
  const body: Record<string, number> = { lat, lon };
  if (areaHa != null) body.area_ha = areaHa;
  const r = await fetch(`${BASE}/api/scan${deep ? "?deep=true" : ""}`, {
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

// N1 — quên / đặt lại / đổi mật khẩu.
export function forgotPassword(email: string) {
  return postJson<{ message: string; dev_link?: string }>(
    "/api/auth/forgot", { email }, "Không gửi được yêu cầu");
}
export function resetPassword(token: string, password: string) {
  return postJson<{ message: string }>(
    "/api/auth/reset", { token, password }, "Không đặt lại được mật khẩu");
}
export function changePassword(oldPassword: string, newPassword: string) {
  return authed<{ message: string }>("/api/auth/change-password",
    { method: "POST", body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }) },
    "Không đổi được mật khẩu");
}

// Quyền riêng tư: xuất toàn bộ dữ liệu / xoá tài khoản.
export function exportMyData() {
  return authed<Record<string, unknown>>("/api/account/export", { method: "GET" },
    "Không xuất được dữ liệu");
}
export function deleteMyAccount() {
  return authed<void>("/api/account", { method: "DELETE" },
    "Không xoá được tài khoản");
}

// Đ12 — nhật ký kiểm toán: hoạt động nhạy cảm gần đây trên CHÍNH tài khoản này.
export type AuditEntry = {
  at: string; action: string; label: string; detail: string;
};
export function getAccountAudit(limit = 50) {
  return authed<{ entries: AuditEntry[] }>(
    `/api/account/audit?limit=${limit}`, { method: "GET" },
    "Không tải được nhật ký tài khoản");
}

// ---- C06 Heatmap ----
export type HeatCell = {
  lat: number;
  lon: number;
  value: number | null;
  risk: string;
  // Màu do người gọi chỉ định — bản đồ NGÀY ĐẾN mã hoá thời điểm bằng màu,
  // không phải mức độ, nên không dùng được thang màu rủi ro.
  color?: string;
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

// ---- C02 + C06 Dòng thời gian rủi ro trên lưới ----
export type TimelineCell = {
  lat: number;
  lon: number;
  values: number[] | null;
  arrival_day: number | null;
  days_over: number;
};
export type TimelineScenario = {
  label: string;
  rain_mult: number;
  temp_delta: number;
  cells: TimelineCell[];
  n_over_by_day: number[];
  first_arrival_day: number | null;
  cells_affected: number;
  max_days_over: number;
};
export type TimelineResolution = {
  cell_km: number;
  effective_km: number;
  native_weather_km: number;
  oversampled: boolean;
  cells_per_data_pixel: number | null;
  note: string;
  why: string;
};
export type TimelineResult = {
  available: boolean;
  message?: string;
  module_id?: string;
  module_name?: string;
  unit?: string;
  center?: { lat: number; lon: number };
  radius_km?: number;
  side?: number;
  cell_dlat?: number;
  cell_dlon?: number;
  dates?: string[];
  scenarios?: TimelineScenario[];
  safe?: number;
  warning?: number;
  calibrated?: boolean;
  headline?: string;
  resolution?: TimelineResolution;
  caveat?: string;
};

export function runTimeline(
  moduleId: string, lat: number, lon: number, side = 7, radiusKm = 8,
) {
  return postJson<TimelineResult>(
    `/api/heatmap/${moduleId}/timeline?side=${side}&radius_km=${radiusKm}`,
    { lat, lon }, "Không dựng được dòng thời gian");
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

async function getJson<T>(path: string, err: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await errMessage(r, err));
  return r.json();
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

// =====================================================================
//  Các luồng trước đây chỉ có backend mà không có đường nào chạm tới từ
//  giao diện. Một luồng người dùng không bấm được thì với họ nó không tồn
//  tại — và với vòng học của phần mềm thì nó còn tệ hơn thế: S05/S09 chỉ
//  sống được nếu U04 có chỗ để người dùng gửi quan sát về.
// =====================================================================

// ---- S04 Twin Genome ----
export type GenomeFeature = { label: string; unit: string };
export type GenomeCompare = {
  feature: string;
  label: string;
  unit: string;
  yours: number;
  theirs: number;
  diff: number;
};
export type GenomeTwin = {
  lat: number;
  lon: number;
  similarity_pct: number;
  distance_km: number;
  genome: Record<string, number>;
  comparison: GenomeCompare[];
};
export type GenomeResult = {
  available: boolean;
  message?: string;
  location?: { lat: number; lon: number };
  your_genome?: Record<string, number>;
  feature_labels?: Record<string, GenomeFeature>;
  twins?: GenomeTwin[];
  reference?: {
    land_cells: number;
    grid_step_deg: number;
    reference_year: number;
    cached: boolean;
  };
  headline?: string;
  why_useful?: string;
  caveat?: string;
  method?: string;
};

export function runGenome(lat: number, lon: number, k = 5) {
  return postJson<GenomeResult>(`/api/genome?k=${k}`, { lat, lon },
    "Không tìm được vùng tương đồng");
}

// ---- C04 Time-Lapse ----
export type TimeLapseFrame = {
  year: number;
  peak: number;
  date: string;
  risk_level: string;
};
export type TimeLapseResult = {
  available: boolean;
  module_id?: string;
  module_name?: string;
  unit?: string;
  from_year?: number;
  to_year?: number;
  frames?: TimeLapseFrame[];
  trend?: string;
  trend_change?: number;
  early_mean?: number;
  late_mean?: number;
  danger_years?: number;
  worst_year?: TimeLapseFrame;
  safe?: number;
  warning?: number;
  headline?: string;
  caveat?: string;
  method?: string;
};

export function runTimeLapse(moduleId: string, lat: number, lon: number, years = 10) {
  return postJson<TimeLapseResult>(
    `/api/timelapse/${moduleId}?years=${years}`, { lat, lon },
    "Không dựng được time-lapse");
}

// ---- U03 Generative Design Studio ----
export type DesignOption = {
  code: string;
  name: string;
  icon: string;
  score: number;
  reasons: string[];
  warnings: string[];
};
export type DesignInfra = { priority: string; item: string; why: string };
export type DesignResult = {
  location: { lat: number; lon: number };
  site: Record<string, unknown>;
  recommended: DesignOption;
  options: DesignOption[];
  infrastructure: DesignInfra[];
  headline: string;
  generative_note: string;
  caveat: string;
};

export function runDesign(lat: number, lon: number) {
  return postJson<DesignResult>("/api/design", { lat, lon },
    "Không sinh được phương án");
}

// ---- U02 Chợ tri thức ----
export type KnowledgeNote = {
  id: number;
  lat: number;
  lon: number;
  title: string;
  body: string;
  topic: string;
  author_name: string;
  helpful_count: number;
  created_at: string;
  similarity_pct?: number;
};
export type KnowledgeResult = {
  available: boolean;
  matched_by: string | null;
  notes: KnowledgeNote[];
  message?: string;
  why?: string;
  note?: string;
};

export function findKnowledge(lat: number, lon: number, topic?: string, k = 5) {
  const q = new URLSearchParams({ lat: String(lat), lon: String(lon), k: String(k) });
  if (topic) q.set("topic", topic);
  return getJson<KnowledgeResult>(`/api/knowledge?${q}`,
    "Không tải được kinh nghiệm chia sẻ");
}

export function shareKnowledge(
  lat: number, lon: number, title: string, body: string, topic: string,
) {
  return authed<KnowledgeNote>("/api/knowledge", {
    method: "POST",
    body: JSON.stringify({ location: { lat, lon }, title, body, topic }),
  }, "Không chia sẻ được");
}

export function markHelpful(id: number) {
  return authed<KnowledgeNote>(`/api/knowledge/${id}/helpful`, { method: "POST" },
    "Không đánh dấu được");
}

// ---- U04 Vòng khép kín: hành động + kết quả ----
export type ActionRow = {
  id: number;
  module_id: string;
  recommendation: string;
  status: string;
  acted_on: string;
  note: string;
  outcome: string | null;
  outcome_note: string;
  created_at: string;
};
export type LoopStage = { stage: string; count: number };
export type LoopStatus = {
  closed: boolean;
  stages: LoopStage[];
  actions_taken: number;
  outcomes_verified: number;
  helped_count: number;
  help_rate: number | null;
  headline: string;
  note: string;
};

export function logAction(
  moduleId: string, recommendation: string, actedOn: string,
  status = "done", note = "", alertId?: number,
) {
  return authed<ActionRow>("/api/actions", {
    method: "POST",
    body: JSON.stringify({
      module_id: moduleId, recommendation, acted_on: actedOn,
      status, note, alert_id: alertId ?? null,
    }),
  }, "Không ghi được hành động");
}

export function recordOutcome(id: number, outcome: string, note = "") {
  return authed<ActionRow>(`/api/actions/${id}/outcome`, {
    method: "POST",
    body: JSON.stringify({ outcome, outcome_note: note }),
  }, "Không ghi được kết quả");
}

export function listActions() {
  return authed<ActionRow[]>("/api/actions", { method: "GET" },
    "Không tải được nhật ký hành động");
}

export function getLoop() {
  return authed<LoopStatus>("/api/loop", { method: "GET" },
    "Không tải được trạng thái vòng học");
}

// ---- S05 Quan sát thực địa (nguồn nuôi cả S04/S05/S09) ----
export type ObservationRow = {
  id: number;
  lat: number;
  lon: number;
  module_id: string;
  observed_on: string;
  outcome: string;
  severity: string | null;
  note: string;
  model_index: number | null;
  created_at: string;
};

export function addObservation(
  lat: number, lon: number, moduleId: string, observedOn: string,
  outcome: "occurred" | "none", severity?: string | null, note = "",
) {
  return authed<ObservationRow>("/api/observations", {
    method: "POST",
    body: JSON.stringify({
      location: { lat, lon }, module_id: moduleId, observed_on: observedOn,
      outcome, severity: severity ?? null, note,
    }),
  }, "Không gửi được quan sát");
}

export function listObservations() {
  return authed<ObservationRow[]>("/api/observations", { method: "GET" },
    "Không tải được quan sát");
}

// ---- S05 Bảng hiệu chỉnh tổng hợp (công khai, đã ẩn danh) ----
export type FederatedAdjustment = {
  cell: string;
  module_id: string;
  threshold_shift: number;
  observations: number;
  hit: number;
  missed: number;
  false_alarm: number;
  correct_quiet: number;
  direction: string;
};
export type FederatedStatus = {
  grid_deg: number;
  min_observations: number;
  max_shift: number;
  total_observations: number;
  contributors: number;
  cells_published: number;
  cells_pending: number;
  adjustments: FederatedAdjustment[];
  privacy: string;
  headline?: string;
};

export function getFederated() {
  return getJson<FederatedStatus>("/api/federated",
    "Không tải được bảng hiệu chỉnh");
}

// ---- S09 Chấm điểm mô hình ----
export type ModelMetrics = {
  hit: number;
  false_alarm: number;
  miss: number;
  correct_negative: number;
  samples: number;
  pod: number | null;
  far: number | null;
  csi: number | null;
  bias: number | null;
};
export type ModelEval = {
  dataset: {
    observations: number;
    modules_covered: number;
    cells_covered: number;
    warn_threshold: number;
  };
  overall: ModelMetrics;
  overall_verdict: string;
  by_module: Record<string, ModelMetrics & { verdict?: string }>;
  weakest_cells: unknown[];
  headline: string;
  metric_guide: Record<string, string>;
  why_csi_first?: string;
};

export function getModelEval() {
  return getJson<ModelEval>("/api/model/evaluate", "Không chấm được mô hình");
}

// ---- C01 Twin đã lưu ----
export type TwinSummary = {
  id: number;
  name: string;
  lat: number;
  lon: number;
  area_ha: number | null;
  score: number | null;
  grade: string | null;
  built_at: string;
};

export function listTwins() {
  return authed<TwinSummary[]>("/api/twins", { method: "GET" },
    "Không tải được danh sách Twin");
}

export function buildTwin(name: string, lat: number, lon: number, areaHa?: number) {
  const location: Record<string, number> = { lat, lon };
  if (areaHa != null) location.area_ha = areaHa;
  return authed<{ id: number; name: string }>("/api/twins", {
    method: "POST", body: JSON.stringify({ name, location }),
  }, "Không dựng được Twin");
}

export function getTwin(id: number) {
  return authed<Record<string, unknown>>(`/api/twins/${id}`, { method: "GET" },
    "Không mở được Twin");
}

export function deleteTwin(id: number) {
  return authed<void>(`/api/twins/${id}`, { method: "DELETE" },
    "Không xoá được Twin");
}

// ---- C11 Bring-Your-Own-Data ----
export type DatasetRow = {
  id: number;
  name: string;
  kind: string;
  row_count: number;
  created_at: string;
};

export function listDatasets() {
  return authed<DatasetRow[]>("/api/datasets", { method: "GET" },
    "Không tải được dữ liệu đã tải lên");
}

export function uploadDataset(name: string, kind: "csv" | "geojson", content: string) {
  return authed<DatasetRow>("/api/datasets", {
    method: "POST", body: JSON.stringify({ name, kind, content }),
  }, "Không tải lên được");
}

export function scoreDataset(id: number, limit = 50) {
  return authed<Record<string, unknown>>(
    `/api/datasets/${id}/score?limit=${limit}`, { method: "POST" },
    "Không chấm điểm được");
}

export function deleteDataset(id: number) {
  return authed<void>(`/api/datasets/${id}`, { method: "DELETE" },
    "Không xoá được");
}

// ---- C12 Khoá API ----
export type ApiKeyRow = {
  id: number;
  label: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
  calls_total: number;
  calls_period: number;
  period: string;
  monthly_quota: number;
  plan: string;
};

export function listKeys() {
  return authed<ApiKeyRow[]>("/api/keys", { method: "GET" }, "Không tải được khoá");
}

export function createKey(label: string, plan = "free") {
  return authed<ApiKeyRow & { key: string }>(
    `/api/keys?label=${encodeURIComponent(label)}&plan=${encodeURIComponent(plan)}`,
    { method: "POST" }, "Không tạo được khoá");
}

// ---- Đối chứng: ngưỡng chung vs hiệu chuẩn ----
// ---- Hồ sơ riêng của thửa đất ----
export type PassportHazard = {
  name: string; events: number; peak_month: number | null;
  peak_month_events?: number; latest: string | null;
  worst_value: number; worst_date: string | null;
  national_threshold: number; note: string;
};

export type Passport = {
  available: boolean;
  message?: string;
  terrain?: {
    elevation_m: number; neighbours_sampled: number; radius_km: number;
    lower_than_pct: number; around_min_m: number; around_max_m: number;
    slope_deg: number | null; meaning: string;
  } | null;
  history?: Record<string, PassportHazard> | null;
  headline?: string | null;
  why_unique: string;
  caveat: string;
};

export function getPassport(lat: number, lon: number) {
  return postJson<Passport>("/api/passport", { location: { lat, lon } },
    "Không dựng được hồ sơ thửa đất");
}

// ---- Ảnh vệ tinh thật của thửa đất ----
export type ImageryLayer = {
  item: string;
  date: string;
  cloud_scene_pct: number;
  true_color: string;
  ndvi: string;
};

export type Imagery = {
  available: boolean;
  message?: string;
  center?: { lat: number; lon: number };
  span_m: number;
  now: ImageryLayer;
  then?: ImageryLayer;
  source: string;
  resolution_m: number;
  caveat: string;
  compare_note: string;
};

export function getImagery(lat: number, lon: number, bufferM = 1200) {
  return postJson<Imagery>("/api/imagery",
    { location: { lat, lon }, buffer_m: bufferM },
    "Không lấy được ảnh vệ tinh");
}

// ---- S10 ③ Ảnh "tương lai": ảnh thật + lớp phủ dự phóng theo kịch bản ----
export type FutureScenario = {
  label: string;
  rain_mult: number;
  temp_delta: number;
  peak: number;
  risk: string;
  risk_vi: string;
  first_danger_date?: string | null;
  intensity: number;
  opacity: number;
  caption: string;
};

export type FutureResult = {
  available: boolean;
  reason?: string;
  message?: string;
  module_id?: string;
  module_name?: string;
  unit?: string;
  safe?: number;
  warning?: number;
  is_real?: boolean;
  confidence?: number;
  confidence_low?: number;
  confidence_high?: number;
  overlay_color?: string;
  layer_label?: string;
  scenarios?: FutureScenario[];
  is_projection?: boolean;
  disclaimer?: string;
  note?: string;
  base_image?: {
    true_color: string;
    date: string;
    cloud_scene_pct?: number;
  } | null;
  base_message?: string;
  span_m?: number;
  resolution_m?: number;
  source?: string;
};

export const FUTURE_MODULES = ["drought", "flood", "wildfire", "landslide"];

export function runFuture(moduleId: string, lat: number, lon: number) {
  return postJson<FutureResult>(`/api/future/${moduleId}`, { lat, lon },
    "Không dựng được ảnh tương lai");
}

export type ModuleContrast = {
  module_id: string;
  windows: number;
  years: number;
  fixed_threshold: number;
  fixed_alarms: number;
  fixed_days_per_year: number;
  calibrated_alarms: number;
  calibrated_days_per_year: number;
  method: string;
};

export function getContrast(lat: number, lon: number) {
  return postJson<{ available: boolean; modules: ModuleContrast[]; message?: string }>(
    "/api/contrast", { location: { lat, lon } }, "Không tính được đối chứng");
}

// ---- Tìm địa điểm theo tên ----
export type PlaceHit = { label: string; lat: number; lon: number; kind: string };

export function searchPlace(q: string) {
  return getJson<{ query: string; results: PlaceHit[]; message?: string }>(
    `/api/place?q=${encodeURIComponent(q)}`, "Không tìm được địa điểm");
}

// ---- Gói cước & bảng kê ----
export type Plan = {
  id: string; name: string; quota: number; price_vnd: number;
  for: string; features: string[];
};

export type PlanCatalogue = {
  plans: Plan[]; currency: string; billing_period: string;
  status: string; disclaimer: string;
};

export function getPlans() {
  return getJson<PlanCatalogue>("/api/plans", "Không tải được bảng giá");
}

export type UsageRow = {
  period: string; plan: string; plan_name: string;
  quota: number | null; used: number; remaining: number | null;
  over_quota: number; calls_total_all_time: number; prefix: string;
  upstream_calls_estimate: number; cash_cost_vnd: number;
  cost_note: string; billing_status: string;
};

export function getUsage() {
  return authed<{
    keys: UsageRow[]; total_calls_this_period: number;
    billing_status: string; next_step: string;
  }>("/api/usage", { method: "GET" }, "Không tải được bảng kê");
}

// ---- Mô hình đã huấn luyện ----
export type ModelEvent = {
  label: string; site: string; detected: boolean;
  in_scope: boolean; lead_days: number | null;
};

export type ModelCard = {
  available: boolean;
  message?: string;
  enabled?: boolean;
  trained_at?: string;
  train_period?: [string, string];
  test_period?: [string, string];
  sites?: number;
  train_days?: number;
  test_days?: number;
  features?: string[];
  regimes?: { id: number; days: number; sites: string[] }[];
  comparison?: {
    alarm_rate: number;
    joint_detected: number; baseline_detected: number;
    joint_events: ModelEvent[]; baseline_events: ModelEvent[];
  }[];
  leave_one_out?: { site: string; label: string; detected: boolean; lead: number | null }[];
  verdict?: string;
  role?: string;
  method?: string;
};

export function getModelCard() {
  return getJson<ModelCard>("/api/model", "Không tải được thẻ mô hình");
}

export type AnomalyMl = {
  available: boolean;
  message?: string;
  date?: string;
  percentile?: number;
  verdict?: string;
  regime?: number;
  top_drivers?: { feature: string; share: number }[];
  role?: string;
  caveat?: string;
};

export function runAnomalyMl(lat: number, lon: number) {
  return postJson<AnomalyMl>("/api/anomaly-ml", { location: { lat, lon } },
    "Không chấm được độ hiếm tổ hợp");
}

export function revokeKey(id: number) {
  return authed<void>(`/api/keys/${id}`, { method: "DELETE" },
    "Không thu hồi được khoá");
}

// ---- U01 Kênh gửi cảnh báo ----
export type ChannelRow = {
  id: number;
  kind: string;
  target: string;
  min_level: string;
  enabled: boolean;
  created_at: string;
  last_sent_at: string | null;
  last_error: string | null;
};

export function listChannels() {
  return authed<ChannelRow[]>("/api/channels", { method: "GET" },
    "Không tải được kênh gửi");
}

export function createChannel(
  kind: "webhook" | "email", target: string, minLevel: "warning" | "danger",
) {
  return authed<ChannelRow>("/api/channels", {
    method: "POST",
    body: JSON.stringify({ kind, target, min_level: minLevel }),
  }, "Không thêm được kênh");
}

export function testChannel(id: number) {
  return authed<Record<string, unknown>>(`/api/channels/${id}/test`,
    { method: "POST" }, "Không gửi thử được");
}

export function deleteChannel(id: number) {
  return authed<void>(`/api/channels/${id}`, { method: "DELETE" },
    "Không xoá được kênh");
}

// H5 — kênh nào đã cấu hình xong PHÍA MÁY CHỦ. Công khai, không lộ token: giao
// diện cần biết trước khi người dùng gõ số vào một kênh chưa bao giờ gửi được.
export type ChannelStatus = {
  ready: { zalo: boolean; telegram: boolean; email: boolean; webhook: boolean };
  note: Record<string, string>;
};
export function getChannelStatus() {
  return getJson<ChannelStatus>("/api/channels/status",
    "Không tải được trạng thái kênh");
}

// H4 — dòng thời gian của MỘT thửa: đã báo gì, hoá ra đúng/hụt/đang chờ, và câu
// nào đang chờ trả lời. Kể cả lần BỎ SÓT (was_warned=false) — không giấu.
export type PlotTimelineEvent = {
  alert_id: number;
  at: string;
  module_id: string;
  risk_level: string;
  headline: string;
  recommendation: string;
  was_warned: boolean;
  outcome: string | null;
  observed_peak: number | null;
  verify_source: string;
  verify_note: string;
};
export type PlotTimeline = {
  plot: {
    id: number; name: string; lat: number; lon: number;
    area_ha: number | null; score: number | null; grade: string | null;
    saved_at: string;
  };
  window_days: number;
  events: PlotTimelineEvent[];
  tally: Record<string, number>;
  questions: TapQuestion[];
  watching_since: string;
};
export function getPlotTimeline(plotId: number, days = 90, limit = 30) {
  return authed<PlotTimeline>(
    `/api/plots/${plotId}/timeline?days=${days}&limit=${limit}`,
    { method: "GET" }, "Không tải được dòng thời gian thửa");
}

// ---- C07 Báo cáo MRV carbon ----
export type MrvReport = {
  available: boolean;
  reason?: string;
  message?: string;
  project_name?: string;
  generated_at?: string;
  measured?: Record<string, unknown>;
  estimated?: Record<string, unknown>;
  change_vs_last_year?: Record<string, unknown> | null;
  headline?: string;
  methodology?: Record<string, string>;
  limitations?: string[];
  to_reach_credit_grade?: string[];
  integrity?: Record<string, unknown>;
};

export function runMrv(lat: number, lon: number, projectName = "", agbTHa?: number) {
  return postJson<MrvReport>("/api/mrv", {
    location: { lat, lon }, project_name: projectName,
    agb_t_ha: agbTHa ?? null,
  }, "Không lập được báo cáo MRV");
}

// ---- Trạng thái vệ tinh & 26 luồng ----
export type SatelliteStatus = {
  configured: boolean;
  client_id_hint: string | null;
  provider: string;
  indices: Record<string, string>;
  message: string;
  unlocks: string[];
};

export function getSatellite() {
  return getJson<SatelliteStatus>("/api/satellite",
    "Không đọc được trạng thái vệ tinh");
}

export type RoadmapFlow = {
  id: string;
  name: string;
  tier: string;
  tier_name: string;
  status: string;
  note: string;
  requires: string | null;
  awaiting_config: boolean;
  awaiting_note: string | null;
};
export type Principle = { name: string; status: string; note: string };
export type Roadmap = {
  total: number;
  done: number;
  partial: number;
  blocked: number;
  live: number;
  awaiting_config: number;
  satellite_configured: boolean;
  flows: RoadmapFlow[];
  by_tier: Record<string, { name: string; total: number; done: number; live: number }>;
  principles: Principle[];
  sectors: { planned: number; covered: number; note: string };
  modules: { total: number; active: number; awaiting_satellite: number };
  headline: string;
  honesty_note: string;
};

// ---- SUP-12 Hồ sơ truy xuất nguồn gốc ----
export type Provenance = {
  available: boolean;
  message?: string;
  product?: string;
  grower?: string;
  generated_at?: string;
  measured?: Record<string, unknown>;
  context?: Record<string, unknown>;
  headline?: string;
  integrity?: Record<string, unknown>;
  scope?: string;
};

export function runProvenance(
  lat: number, lon: number, start: string, end: string,
  product = "", grower = "",
) {
  return postJson<Provenance>("/api/provenance", {
    location: { lat, lon }, start, end, product, grower,
  }, "Không lập được hồ sơ truy xuất");
}

// ---- Hàng đợi việc chạy nền ----
export type JobStatus = {
  id: string;
  kind: string;
  label: string;
  state: "queued" | "running" | "done" | "error";
  queued_s: number;
  elapsed_s: number;
  result?: unknown;
  error?: string;
  message?: string;
};

export function getJob(id: string) {
  return getJson<JobStatus>(`/api/jobs/${id}`, "Không đọc được trạng thái việc");
}

// ---- C08 Tổng quan danh mục theo vùng ----
export type PortfolioDriver = {
  id: string;
  name: string;
  icon: string;
  risk_level: string;
  headline: string;
};
export type PortfolioPlot = {
  plot_id: number;
  name: string;
  lat: number;
  lon: number;
  area_ha: number | null;
  risk_level: string;
  score: number | null;
  grade: string | null;
  drivers: PortfolioDriver[];
};
export type PortfolioCell = {
  cell: string;
  plots: number;
  area_ha: number;
  danger: number;
  warning: number;
  safe: number;
  unknown: number;
  at_risk_pct: number;
  top_driver: string | null;
};
export type PortfolioOverview = {
  available: boolean;
  message?: string;
  plots_scanned?: number;
  plots_total?: number;
  truncated?: boolean;
  counts?: Record<string, number>;
  total_ha?: number;
  at_risk_ha?: number;
  bbox?: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  cells?: PortfolioCell[];
  cell_deg?: number;
  plots?: PortfolioPlot[];
  headline?: string;
  method?: string;
  caveat?: string;
};

export function getPortfolioOverview() {
  return authed<PortfolioOverview>("/api/plots/overview", { method: "GET" },
    "Không quét được danh mục");
}

export function getRoadmap() {
  return getJson<Roadmap>("/api/roadmap", "Không tải được trạng thái luồng");
}

// ---- KẾ HOẠCH THỬA CỦA BẠN (gom 4 hướng: việc cần làm · ngày an toàn ·
//      giá trị chịu rủi ro · tự canh) ----
export type PlanAction = {
  id: string;
  name: string;
  icon: string;
  risk_level: string;
  headline: string;
  do: string;
  when: string | null;
  when_weekday: string;
  lead_days: number | null;
  peak: number | null;
  unit: string | null;
  can_ask: boolean;
};
export type PlanDay = {
  date: string;
  weekday: string;
  safe: boolean;
  hazards: string[];
};
export type PlanValueItem = {
  id: string;
  name: string;
  icon: string;
  loss_pct: [number, number];
  stake_lo: number;
  stake_hi: number;
  stake_text: string;
  lead_days: number | null;
};
export type PlanValue = {
  available: boolean;
  at_risk: boolean;
  crop: string;
  crop_label: string;
  crop_value_range: [number, number];
  area_ha: number | null;
  per_unit: boolean;
  items: PlanValueItem[];
  worst_lo: number;
  worst_hi: number;
  plot_lo: number;
  plot_hi: number;
  plot_text: string;
  headline: string;
  assumption: string;
};
export type PlanWatch = {
  grade: string;
  score: number;
  n_alerts: number;
  real_data_ratio: number;
  headline: string;
  capability: string;
};
export type PlanCrop = { id: string; label: string };
export type PlotPlan = {
  serviceable: boolean;
  message?: string;
  location?: { lat: number; lon: number };
  generated_at?: string;
  n_alerts?: number;
  actions?: PlanAction[];
  safe_window?: { days: PlanDay[]; safe_dates: string[]; headline: string };
  value?: PlanValue;
  watch?: PlanWatch;
  crops?: PlanCrop[];
};

export function getPlan(lat: number, lon: number, areaHa?: number, crop = "lua") {
  const body: Record<string, number> = { lat, lon };
  if (areaHa != null) body.area_ha = areaHa;
  return postJson<PlotPlan>(`/api/plan?crop=${encodeURIComponent(crop)}`, body,
    "Không dựng được kế hoạch thửa");
}

// ---- VÒNG LẶP TIN CẬY: sổ điểm tự chấm + một chạm (moat) ----
export type ScorecardRates = {
  pod_pct: number | null;   // bắt được bao nhiêu % số đợt thực tế
  far_pct: number | null;   // báo bừa
  csi_pct: number | null;   // điểm tổng hợp
};
export type ScorecardModule = ScorecardRates & {
  module_id: string;
  name: string;
  scored: number;
  counts: Record<string, number>;
  enough: boolean;
};
export type GroundTruth = {
  observations: number;
  by_source: Record<string, number>;
  by_onetap: number;
  cells_covered: number;
  note: string;
};
export type Scorecard = ScorecardRates & {
  window_days: number;
  module_id: string | null;
  counts: Record<string, number>;
  scored: number;
  pending: number;
  verified_by_people: number;
  enough: boolean;
  min_sample: number;
  headline: string;
  method: string;
  by_module: ScorecardModule[];
  ground_truth: GroundTruth;
};

export function getScorecard(days = 90) {
  return getJson<Scorecard>(`/api/scorecard?days=${days}`,
    "Không tải được sổ điểm");
}

// A9/G1 — ký tờ trình rủi ro bằng mã băm để bên nhận tự kiểm bản in không bị sửa.
export type SignedReport = {
  hash: string; short: string; signed_at: string; verify_note: string;
  [k: string]: unknown;
};
export function signReport(facts: Record<string, unknown>) {
  return postJson<SignedReport>("/api/report/sign", facts,
    "Không ký được báo cáo");
}

// A3 — dự báo xác suất 7 ngày tới từ tổ hợp vật lý (P10/P50/P90 + % vượt ngưỡng).
export type ProbForecast = {
  available: boolean;
  message?: string;
  module_id?: string;
  members?: number;
  p10?: number; p50?: number; p90?: number;
  prob_exceed_warning?: number;
  prob_exceed_watch?: number;
  sentence?: string;
};
export function getProbability(moduleId: string, lat: number, lon: number) {
  return postJson<ProbForecast>(`/api/probability/${encodeURIComponent(moduleId)}`,
    { lat, lon }, "Không tính được xác suất");
}

// A2 — rào chắn số: đã chặn bao nhiêu lần LLM bịa số (công bố như sổ điểm).
export type GuardStats = {
  checked: number; redacted_answers: number; numbers_removed: number; note: string;
};
export function getGuardStats() {
  return getJson<GuardStats>("/api/guard/stats", "Không tải được thống kê rào chắn");
}

export type ScorecardBucket = ScorecardRates & {
  from: string; to: string; counts: Record<string, number>; scored: number;
};
export function getScorecardTimeline(days = 180, buckets = 12) {
  return getJson<{ buckets: ScorecardBucket[] }>(
    `/api/scorecard/timeline?days=${days}&buckets=${buckets}`,
    "Không tải được xu hướng sổ điểm");
}

// Bản đồ độ tin cậy — phần mềm ĐÃ được kiểm chứng ở ĐÂU (theo ô lưới ~55 km).
export type ReliabilityCell = ScorecardRates & {
  cell: string;
  lat: number;
  lon: number;
  scored: number;
  hit: number;
  miss: number;
  false_alarm: number;
  enough: boolean;
  label: string;
  grid_deg: number;
};
export type ReliabilityResult = {
  cells: ReliabilityCell[];
  window_days: number;
  module_id: string | null;
  min_cell_sample: number;
  grid_deg: number;
  note: string;
};
export function getReliability(days = 365, moduleId?: string) {
  const q = new URLSearchParams({ days: String(days) });
  if (moduleId) q.set("module_id", moduleId);
  return getJson<ReliabilityResult>(`/api/reliability?${q}`,
    "Không tải được bản đồ độ tin cậy");
}

// ---- Một chạm: câu hỏi công khai sau link cảnh báo (KHÔNG cần đăng nhập) ----
export type TapOption = { value: "yes" | "no" | "unsure"; label: string };
export type TapQuestion = {
  alert_id: number;
  module_id: string;
  asked_on: string;
  headline: string;
  question: string;
  options: TapOption[];
  answered: boolean;
  outcome: string | null;
  why: string;
  token?: string;
};
export type TapResult = {
  already: boolean;
  outcome: string | null;
  message: string;
  // M5 — đóng góp vừa rồi có ích thế nào (quan sát thứ mấy ở vùng, còn mấy lần).
  contribution?: {
    count_in_region: number;
    min_needed: number;
    remaining: number;
    enough: boolean;
    message: string;
  };
};

export function getTapQuestion(token: string) {
  return getJson<TapQuestion>(`/api/tap/${encodeURIComponent(token)}`,
    "Liên kết không hợp lệ hoặc đã hết hạn");
}
export function sendTapAnswer(token: string, answer: "yes" | "no" | "unsure") {
  return postJson<TapResult>(`/api/tap/${encodeURIComponent(token)}`, { answer },
    "Không gửi được câu trả lời");
}

// Câu hỏi đang chờ CHÍNH người này trả lời — để đóng vòng ngay trong app.
export function getMyQuestions(limit = 5) {
  return authed<{ questions: TapQuestion[]; count: number }>(
    `/api/questions?limit=${limit}`, { method: "GET" },
    "Không tải được câu hỏi cần bạn xác nhận");
}
