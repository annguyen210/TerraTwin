const BASE = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

// Ngôn ngữ hiện tại để gửi cho máy chủ (nội dung động: tên mô-đun, headline,
// recommendation…). LangProvider lưu vào localStorage "terratwin_lang".
export function curLang(): string {
  if (typeof window === "undefined") return "vi";
  try { return localStorage.getItem("terratwin_lang") === "en" ? "en" : "vi"; }
  catch { return "vi"; }
}
const _lp = (extra = ""): string => `${extra ? extra + "&" : "?"}lang=${curLang()}`;

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
    if (typeof d?.detail?.message === "string") return d.detail.message;
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
  heavy?: boolean;
  // false = mô-đun thông tin/cơ hội (điện mặt trời, năng suất, carbon…): risk_level
  // là mức trên thang RIÊNG của nó, không phải nguy hiểm — xem lib/riskScale.ts.
  threat?: boolean;
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
  const r = await fetch(`${BASE}/api/modules${_lp()}`);
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
  const r = await fetch(`${BASE}/api/assess/${moduleId}${_lp()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không lấy được đánh giá"));
  return r.json();
}

export async function getTerraScore(lat: number, lon: number): Promise<TerraScore> {
  const r = await fetch(`${BASE}/api/terrascore${_lp()}`, {
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
  const r = await fetch(`${BASE}/api/copilot${_lp()}`, {
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
  threat?: boolean;
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
  const r = await fetch(`${BASE}/api/scan${_lp(deep ? "?deep=true" : "")}`, {
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
// N8 — ba mục đích tách riêng: nhận cảnh báo · góp quan sát · phục vụ nghiên cứu.
export type AuthUser = {
  id: number; email: string; name: string; role?: string; email_verified?: boolean;
  consent_alerts?: boolean; consent_observations?: boolean; consent_research?: boolean;
  coop_code?: string; share_with_coop?: boolean;   // Đ11
};
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

// N8 — đổi lựa chọn đồng ý theo từng mục đích. Chỉ gửi trường muốn đổi.
export function updateConsent(consent: {
  consent_alerts?: boolean; consent_observations?: boolean; consent_research?: boolean;
}) {
  return authed<AuthUser>("/api/account/consent",
    { method: "PUT", body: JSON.stringify(consent) },
    "Không lưu được lựa chọn đồng ý");
}

// N1 — xác thực email.
export function verifyEmail(token: string) {
  return postJson<{ message: string; already_verified: boolean }>(
    "/api/auth/verify-email", { token }, "Không xác thực được email");
}
export function resendVerification() {
  return authed<{ message: string; sent: boolean }>("/api/auth/resend-verification",
    { method: "POST" }, "Không gửi lại được liên kết xác thực");
}

// M5 — "bạn đã góp N quan sát · khu vực của bạn đã được xác minh M lần" trên
// trang cá nhân. Số thật lấy từ Observation/Alert của chính người dùng.
export type Contribution = { observations_contributed: number; alerts_verified: number; alerts_hit: number };
export function getContribution() {
  return authed<Contribution>("/api/account/contribution", { method: "GET" },
    "Không tải được đóng góp của bạn");
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
  return postJson<AskResult>(`/api/ask${_lp()}`,
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

export type RadarProgress = { done: number; total: number; current: string };

type RadarJob = {
  job_id?: string;
  state?: "queued" | "running" | "done" | "error";
  progress?: RadarProgress;
  result?: RadarRun;
  message?: string;
};

// "Rà soát ngay" CHẠY NỀN: máy chủ trả job_id ngay rồi quét ở worker (3 thửa
// đo được 196–519 giây — giữ một kết nối ngần ấy thì proxy cắt). Hàm này đẩy
// việc, rồi hỏi tiến độ mỗi 3 giây cho tới khi xong; `onProgress` để giao diện
// hiện "thửa 2/3" thay vì một vòng xoay vô định mà người dùng tưởng treo.
export async function runRadar(onProgress?: (p: RadarProgress) => void): Promise<RadarRun> {
  const first = await authed<RadarRun & RadarJob>(`/api/radar/run${_lp()}`,
    { method: "POST" }, "Không chạy được rà soát");
  if (!first.job_id) return first;          // chưa có thửa / máy chủ chạy tại chỗ

  const deadline = Date.now() + 20 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 3000));
    const st = await authed<RadarJob>(`/api/radar/run/${first.job_id}`,
      { method: "GET" }, "Không hỏi được tiến độ rà soát");
    if (st.progress && onProgress) onProgress(st.progress);
    if (st.state === "done" && st.result) return st.result;
    if (st.state === "error") throw new Error(st.message || "Rà soát gặp lỗi");
  }
  throw new Error("Rà soát chạy quá lâu — kết quả vẫn sẽ hiện trong danh sách cảnh báo khi xong.");
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
  return postJson<ExplainResult>(`/api/explain/${moduleId}${_lp()}`, { lat, lon },
    "Không phân tích được nguyên nhân");
}

export function runGoalSeek(moduleId: string, lat: number, lon: number) {
  return postJson<GoalSeekResult>(`/api/goalseek/${moduleId}${_lp()}`, { lat, lon },
    "Không chạy được mô phỏng ngược");
}

export function runTimeMachine(moduleId: string, lat: number, lon: number) {
  return postJson<TimeMachineResult>(`/api/timemachine/${moduleId}${_lp()}`, { lat, lon },
    "Không chạy được cỗ máy thời gian");
}

// A7 — phát hiện mất tán cây bền vững trên chuỗi NDVI theo tháng (BFAST/CUSUM).
export type ChangeDetectResult = {
  available: boolean;
  reason?: string;
  message: string;
  n_scenes?: number;
  window?: [string, string];
  change_detected?: boolean;
  change_date?: string | null;
  level_shift_ndvi?: number;
  test_statistic?: number;
  threshold?: number;
};
export function changeDetect(lat: number, lon: number, months = 24) {
  return postJson<ChangeDetectResult>(`/api/change-detect?${_lp(`months=${months}`)}`, { lat, lon },
    "Không phát hiện được biến động");
}

// A8 — tự vẽ ranh thửa bằng watershed trên độ dốc NDVI quanh điểm bấm.
export type AutoBoundaryResult = {
  available: boolean;
  reason?: string;
  message: string;
  area_ha?: number;
  pixel_size_m?: number;
  grid_size?: number;
  bbox?: [number, number, number, number];
  scene?: string;
  scene_date?: string;
  outline_rows?: [number, number, number][];
};
export function autoBoundary(lat: number, lon: number, bufferM = 500) {
  return postJson<AutoBoundaryResult>(`/api/auto-boundary?${_lp(`buffer_m=${bufferM}`)}`, { lat, lon },
    "Không tự vẽ được ranh thửa");
}

export function runAnomaly(lat: number, lon: number) {
  return postJson<AnomalyResult>(`/api/anomaly${_lp()}`, { lat, lon },
    "Không so sánh được với khí hậu nền");
}

export async function getBacktests(): Promise<BacktestEvent[]> {
  const r = await fetch(`${BASE}/api/backtest${_lp()}`);
  if (!r.ok) throw new Error("Không tải được danh sách backtest");
  return r.json();
}

export async function runBacktest(eventId: string): Promise<BacktestResult> {
  const r = await fetch(`${BASE}/api/backtest/${eventId}${_lp()}`);
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
  return postJson<GenomeResult>(`/api/genome?k=${k}&lang=${curLang()}`, { lat, lon },
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
export type DesignInfra = { priority: string; priority_code?: string; item: string; why: string };
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
  method?: { counting: string; cross_module: string };
};

export function getPassport(lat: number, lon: number) {
  return postJson<Passport>(`/api/passport${_lp()}`, { location: { lat, lon } },
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
  return postJson<Imagery>(`/api/imagery${_lp()}`,
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
    `/api/contrast${_lp()}`, { location: { lat, lon } }, "Không tính được đối chứng");
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

export type PilotFeedbackIn = {
  role: "farmer" | "coop" | "exporter" | "other"; ease: number; trust: number;
  would_use: "yes" | "maybe" | "no";
  hardest: "boundary" | "screen" | "dossier" | "lot" | "verify" | "none";
  minutes: number | null; region: string; comment: string; contact: string;
  consent_contact: boolean; source: "web" | "paper";
};

export function sendPilotFeedback(body: PilotFeedbackIn) {
  return authed<{ ok: boolean; id: number; message: string }>(`/api/pilot/feedback?lang=${curLang()}`,
    { method: "POST", body: JSON.stringify(body) }, "Không gửi được góp ý");
}

// ---------- Gán nhãn kiểm định EUDR v3 (người giải đoán ảnh 2020) ----------
export type LabelBox = { left: number; top: number; width: number; height: number };
export type LabelView = {
  cell: number; center: { lat: number; lon: number }; bounds: number[]; area_ha: number; mosaic_box: LabelBox;
  wayback: Record<"before" | "after", { release_date: string; acquired: string | null; resolution_m: number | null;
                                        source: string | null; tiles: string[][] }>;
  s2: Record<string, { date: string; cloud_pct: number; url: string; box: LabelBox } | null>;
};
export type LabelCover = "natural_forest" | "planted_forest" | "tree_crop" | "no_trees" | "unclear";
export type LabelIn = { cover2020: LabelCover; loss: "yes" | "no" | "unclear"; confidence: number;
                        seconds?: number | null; note: string };
export type LabelNext = { done: boolean; labeled: number; n_cells: number; position?: number;
                          view?: LabelView; mine?: LabelIn | null };
export type LabelSummary = { n_cells: number; per_labeler: { email: string; labeled: number }[];
  truth_counts: Record<"T_lost" | "T_forest" | "T_clean", number>; cells_2plus: number;
  excluded: Record<string, number>; kappa_forest: number | null; agree_forest: number | null; min_n_per_set: number };

export function labelMe() {
  return authed<{ can_label: boolean; n_cells: number; done: number; sample_ready: boolean }>(
    "/api/label/v3/me", { method: "GET" }, "Không tải được trạng thái gán nhãn");
}
export function labelNext(after?: number) {
  return authed<LabelNext>(`/api/label/v3/next?lang=${curLang()}${after != null ? `&after=${after}` : ""}`,
    { method: "GET" }, "Không tải được ô tiếp theo");
}
export function labelCell(k: number) {
  return authed<LabelNext>(`/api/label/v3/cell/${k}`, { method: "GET" }, "Không tải được ô");
}
export function labelSave(k: number, body: LabelIn) {
  return authed<{ ok: boolean; labeled: number }>(`/api/label/v3/cell/${k}`,
    { method: "POST", body: JSON.stringify(body) }, "Không lưu được nhãn");
}
export function adminLabelers() {
  return authed<{ labelers: { email: string; created_at: string | null }[] }>(
    "/api/admin/label/v3/labelers", { method: "GET" }, "Không tải được danh sách người gán nhãn");
}
export function adminAddLabeler(email: string) {
  return authed<{ ok: boolean }>("/api/admin/label/v3/labelers",
    { method: "POST", body: JSON.stringify({ email }) }, "Không thêm được người gán nhãn");
}
export function adminRemoveLabeler(email: string) {
  return authed<{ ok: boolean }>(`/api/admin/label/v3/labelers/${encodeURIComponent(email)}`,
    { method: "DELETE" }, "Không gỡ được người gán nhãn");
}
export function adminLabelSummary() {
  return authed<LabelSummary>("/api/admin/label/v3/summary", { method: "GET" }, "Không tải được tiến độ gán nhãn");
}
export async function adminLabelExport() {
  const data = await authed<unknown>("/api/admin/label/v3/export", { method: "GET" }, "Không xuất được nhãn");
  const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "eudr-labels-v3.json";
  a.click();
  URL.revokeObjectURL(url);
}

export type PilotBlock = { n: number; ease_mean: number | null; trust_mean: number | null; minutes_median: number | null;
  would_use: Record<"yes" | "maybe" | "no", number>; hardest: Record<string, number> };
export type PilotSummary = { all: PilotBlock; by_role: Record<string, PilotBlock>; note: string;
  latest: { id: number; created_at: string | null; source: string; role: string; region: string; ease: number; trust: number;
            minutes: number | null; would_use: string; hardest: string; comment: string; contact: string }[] };

export function getPilotSummary() {
  return authed<PilotSummary>("/api/admin/pilot/feedback", { method: "GET" }, "Không tải được góp ý thí điểm");
}

export async function downloadPilotCsv() {
  const r = await fetch(`${BASE}/api/admin/pilot/feedback.csv`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await errMessage(r, "Không tải được tệp CSV"));
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "gop-y-thi-diem.csv";
  a.click();
  URL.revokeObjectURL(url);
}

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
  return postJson<AnomalyMl>(`/api/anomaly-ml${_lp()}`, { location: { lat, lon } },
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

// P5/N1 — sức khoẻ máy chủ công khai (trang /status + banner SMTP ở /forgot).
export type HealthStatus = {
  status: "ok" | "degraded";
  service: string;
  modules: number;
  quota: {
    exhausted: string[];
    minutes_since_detected: Record<string, number>;
    count_429_24h: Record<string, number>;
    message: string;
  };
  jobs: Record<string, unknown>;
  email: {
    smtp_configured: boolean;
    forgot_password_works: boolean;
    email_verification_works: boolean;
    message: string | null;
  };
  calls: { total: number; cache_hits: number; hit_rate_pct: number | null };
  radar: { last_sweep_at: string | null; last_sweep: Record<string, unknown> | null };
  database?: { kind: string; provider: string | null; message: string | null };
  // Khoá ký Hồ sơ đất số: "env" (an toàn) / "auto-db" (tự sinh, nằm trong CSDL) / "none".
  signing?: { source: "env" | "auto-db" | "none"; key_id?: string; message: string | null } | null;
  field_photos?: { count: number; bytes: number; avg_kb: number | null; max_mb: number;
                   used_pct: number | null; per_user_limit: number } | null;
};
export function getHealth() {
  return getJson<HealthStatus>("/api/health", "Không tải được trạng thái hệ thống");
}

// Đ11 — trang quản trị. Bốn endpoint này đòi role='admin' (403 nếu không) —
// kiểu trả về giữ lỏng (dict) vì đây là dữ liệu vận hành nội bộ, không phải
// hợp đồng công khai cần khoá kiểu chặt.
export function getFunnel(days = 30) {
  return authed<{ window_days: number; counts: Record<string, number>;
    steps: { step: string; count: number; pct_of_open: number | null }[]; note: string }>(
    `/api/admin/funnel?days=${days}`, { method: "GET" }, "Không tải được phễu người dùng");
}
export function getBackupStatus() {
  return authed<{ configured: boolean; stale: boolean; message: string;
    latest?: string; age_hours?: number; count?: number }>(
    "/api/admin/backup-status", { method: "GET" }, "Không tải được trạng thái sao lưu");
}
export function getDrift() {
  return authed<Record<string, unknown>>(
    "/api/admin/drift", { method: "GET" }, "Không tải được báo cáo trôi");
}

// Đ11 — vai trò coop: xem thửa của thành viên cùng mã nhóm đã bật share_with_coop.
export type CoopPlot = { id: number; name: string; lat: number; lon: number;
  area_ha: number | null; score: number | null; grade: string | null; owner_name: string };
export function getCoopPlots() {
  return authed<{ coop_code: string; members: number; plots: CoopPlot[]; message?: string }>(
    "/api/coop/plots", { method: "GET" }, "Không tải được thửa hợp tác xã");
}
export function updateCoop(body: { coop_code?: string; share_with_coop?: boolean }) {
  return authed<AuthUser>("/api/account/coop",
    { method: "PUT", body: JSON.stringify(body) },
    "Không lưu được cài đặt hợp tác xã");
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
  return postJson<MrvReport>(`/api/mrv${_lp()}`, {
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
// Loại đất THẬT tại thửa — ESA WorldCover 10 m (backend services/landuse.py).
export type LandUseClass = { code: number; name: string; group: string; pct: number };
export type LandUse = {
  source: string;
  year: string | null;
  pixels: number;
  classes: LandUseClass[];
  group_pct: Record<string, number>;
  dominant_group: "tree" | "open" | "crop" | "built" | "water" | "mixed";
  dominant_pct: number;
  label: string;
};
export type PlanValue = {
  available: boolean;
  // false = không quy ra tiền theo cây trồng (đất xây dựng, mặt nước, chưa rõ
  // cây gì) — `assumption` nói lý do, người dùng có thể tự chọn loại cây.
  applicable: boolean;
  at_risk: boolean;
  crop: string | null;
  crop_label: string | null;
  crop_value_range?: [number, number];
  area_ha?: number | null;
  per_unit?: boolean;
  items: PlanValueItem[];
  worst_lo: number;
  worst_hi: number;
  plot_lo?: number;
  plot_hi?: number;
  plot_text?: string;
  headline: string;
  assumption: string;
  land_use: LandUse | null;
  land_use_note?: string | null;
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

// crop bỏ trống → máy chủ tự chọn theo loại đất thật (chỉ giả định lúa ở đất
// trồng trọt). Có crop → người dùng chủ động chọn.
export function getPlan(lat: number, lon: number, areaHa?: number, crop?: string | null) {
  const body: Record<string, number> = { lat, lon };
  if (areaHa != null) body.area_ha = areaHa;
  const q = crop ? `crop=${encodeURIComponent(crop)}&` : "";
  return postJson<PlotPlan>(`/api/plan?${q}lang=${curLang()}`, body,
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
  return getJson<Scorecard>(`/api/scorecard?days=${days}&lang=${curLang()}`,
    "Không tải được sổ điểm");
}

// M4 — bản tin sáng.
export function getBriefStatus() {
  return authed<{ enabled: boolean }>("/api/brief/status", { method: "GET" },
    "Không tải được trạng thái bản tin");
}
export function toggleBrief(on: boolean) {
  return authed<{ enabled: boolean }>(`/api/brief/toggle?on=${on}`,
    { method: "POST" }, "Không đổi được bản tin");
}
export function previewBrief() {
  return authed<{ sent: number; title?: string; body?: string; message?: string }>(
    "/api/brief/preview", { method: "POST" }, "Không gửi thử được bản tin");
}

// M1 — Web Push.
export function getPushKey() {
  return getJson<{ configured: boolean; public_key: string | null }>(
    "/api/push/key", "Không tải được khoá push");
}
export function subscribePush(sub: unknown) {
  return authed<void>("/api/push/subscribe",
    { method: "POST", body: JSON.stringify(sub) }, "Không đăng ký được push");
}
export function testPush() {
  return authed<{ sent: number }>("/api/push/test", { method: "POST" },
    "Không gửi thử được");
}

// A5 — nguồn gốc dữ liệu + công thức tái lập cho một cảnh báo.
export type AlertLineage = {
  alert_id: number;
  inputs: Record<string, unknown>;
  model: { thresholds: { safe: number; warning: number }; note: string;
           calibration: Record<string, unknown> };
  sources: string[];
  reproduce: { steps: string[]; verify_api: string; backtest_api: string } | null;
  verification: Record<string, unknown>;
  lineage_hash: string;
  lineage_short: string;
};
export function getAlertLineage(alertId: number) {
  return authed<AlertLineage>(`/api/explain/${alertId}/lineage`, { method: "GET" },
    "Không tải được nguồn gốc");
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

// ---- HỒ SƠ ĐẤT SỐ: phát hành một lần, ký Ed25519, móc xích sổ đăng ký công khai ----
export type DossierCheck = { id: "content" | "entry" | "signature" | "chain" | "evidence"; ok: boolean; label: string };
export type DossierVerification = { valid: boolean; checks: DossierCheck[] };
export type DossierModule = {
  id: string; name: string; risk_level: string; status: string; is_real: boolean;
  threat?: boolean; headline: string;
};
// Ảnh thực địa ĐÃ KIỂM (backend services/evidence.py) — không bao giờ kèm toạ độ GPS gốc.
export type EvidenceCheck = { id: "gps" | "location" | "time" | "edited" | "duplicate"; ok: boolean | null; label: string };
export type FieldEvidence = {
  id: string;
  verdict: "match" | "review" | "mismatch";
  verdict_label: string;
  checks: EvidenceCheck[];
  distance_m: number | null;
  taken_at: string | null;
  sha256: string;
  phash: string;
  thumb_sha256: string;
  thumb_url: string;
  caveat: string;
  name?: string;
};
export const evidenceThumbSrc = (e: { thumb_url: string }) => `${BASE}${e.thumb_url}`;

async function fileToB64(f: File): Promise<string> {
  // Gửi ẢNH GỐC (còn EXIF). Không thu nhỏ bằng canvas — canvas xoá sạch EXIF.
  const buf = new Uint8Array(await f.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) {
    bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

export async function uploadEvidence(lat: number, lon: number, areaHa: number | null | undefined, file: File) {
  const body: Record<string, unknown> = { lat, lon, name: file.name, data_b64: await fileToB64(file) };
  if (areaHa != null) body.area_ha = areaHa;
  const r = await fetch(`${BASE}/api/evidence?lang=${curLang()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${file.name}: ${await errMessage(r, "Không kiểm được ảnh")}`);
  return (await r.json()) as FieldEvidence;
}

export type DossierFacts = {
  schema: string;
  lang: string;
  // "eudr_plot" = Hồ sơ vườn chuẩn EUDR (xem EudrDossierFacts); vắng = hồ sơ đất số.
  kind?: "eudr_plot";
  location: { lat: number; lon: number; area_ha: number | null };
  land_use: LandUse | null;
  terrain: NonNullable<Passport["terrain"]> | null;
  history_10y: Record<string, PassportHazard> | null;
  history_caveat: string | null;
  // Từ 3/10/2026 hồ sơ KHÔNG ký dự báo (predictions_included=false); hồ sơ cũ vẫn có.
  predictions_included?: boolean;
  predictions_note?: string;
  evidence_classes?: Record<string, string>;
  current_risk?: {
    assessed_at: string;
    terrascore: { score: number; grade: string; summary: string };
    real_data_ratio: number;
    modules: DossierModule[];
    not_assessed_in_dossier: string[];
  } | null;
  track_record?: {
    window_days?: number; scored?: number; pending?: number; enough?: boolean;
    min_sample?: number; headline?: string;
    pod_pct?: number | null; far_pct?: number | null; csi_pct?: number | null;
  } | null;
  sources: string[];
  missing: string[];
  disclaimer: string;
  field_evidence?: FieldEvidence[];
  // Mô hình học sâu TerraTwin trên ảnh Sentinel-2 mới nhất vs WorldCover 2021.
  land_change?: {
    changed: boolean; flags: string[]; headline: string;
    before: { source: string; groups_pct: Record<string, number> };
    now: { source: string; groups_pct: Record<string, number>;
           image: { item: string; date: string; clear_pct_at_plot: number; offset_removed: boolean } };
    delta_pts: Record<string, number>;
    model: { miou_holdout: number | null; holdout_provinces?: string[] };
    caveat: string;
  } | null;
};
export type DossierProof = {
  schema: string; facts_hash: string; prev_hash: string; entry_hash: string;
  algorithm: string; key_id: string; signature: string;
};
export type DossierDoc = { id: string; seq: number; issued_at: string; facts: DossierFacts & Partial<EudrDossierFacts>; proof: DossierProof };
export type Dossier = DossierDoc & {
  url: string; qr: string | null; verification: DossierVerification;
  facts_canonical?: string;
  revealed?: Record<string, { value: string; ok: boolean }>;
  disclosure?: { token: string; url: string; stored: boolean };
  transparency?: { seq: number; leaf_index: number; tree_size: number; leaf_hash: string; root_hash: string; proof: string[];
                   head: { tree_size: number; root_hash: string; timestamp: string; key_id: string; signature: string } } | null;
  monitor?: { checked_at: string; level: string; issued_level: string; changed: boolean; why?: string[];
              reasons?: string[]; s2_after?: string | null } | null;
};
export type DossierFileCheck = {
  valid: boolean; found: boolean; matches_registry?: boolean;
  registry?: DossierVerification; message: string;
};

export async function issueDossier(lat: number, lon: number, areaHa?: number | null, evidenceIds: string[] = []) {
  // Không bắt buộc đăng nhập (người mua đất thường chưa có tài khoản); có token
  // thì gửi kèm để hồ sơ gắn với tài khoản.
  const body: Record<string, unknown> = { lat, lon, evidence_ids: evidenceIds };
  if (areaHa != null) body.area_ha = areaHa;
  const r = await fetch(`${BASE}/api/dossier?lang=${curLang()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không phát hành được hồ sơ đất số"));
  return (await r.json()) as Dossier;
}

export function getDossier(id: string, token?: string | null) {
  return getJson<Dossier>(`/api/dossier/${encodeURIComponent(id)}?lang=${curLang()}${token ? `&d=${encodeURIComponent(token)}` : ""}`,
    "Không tải được hồ sơ");
}

export function verifyDossierFile(doc: unknown) {
  return postJson<DossierFileCheck>(`/api/dossier/verify?lang=${curLang()}`, doc,
    "Không kiểm được tệp hồ sơ");
}

// ---- THẨM ĐỊNH HÀNG LOẠT: CSV nhiều thửa → bảng rủi ro danh mục (cần đăng nhập) ----
export type BatchRow = {
  ref: string; lat: number; lon: number; area_ha: number | null;
  land_group: string | null; land_label: string | null;
  risk_level: "danger" | "warning" | "safe" | "unknown";
  score: number | null; grade: string | null; drivers: string[];
  history_10y: Record<string, number>; real_data_ratio: number | null; error: string | null;
};
export type BatchSummary = {
  n: number; n_ok: number; n_failed: number;
  by_risk: Record<string, number>; by_land: Record<string, number>; grades: Record<string, number>;
  top_drivers: [string, number][]; history_10y_plots: Record<string, number>;
  total_ha: number; at_risk_ha: number; at_risk_pct: number | null;
  watchlist: string[]; headline: string;
};
export type BatchRowError = { line: number; message: string };
export type BatchState = {
  id: string; state: "queued" | "running" | "done" | "error" | null;
  title?: string; created_at?: string;
  // phase "paused_quota": nguồn dữ liệu đang chặn vì quá hạn mức — lô TẠM DỪNG chờ.
  progress?: { done: number; total: number; current: string; phase?: string; detail?: unknown };
  summary?: BatchSummary; rows?: BatchRow[]; error?: string; message?: string;
};
export type BatchRunInfo = { id: string; title: string; n_rows: number; created_at: string; headline: string | null };

export const batchTemplateUrl = () => `${BASE}/api/batch/template`;

export async function submitBatch(csv: string, title: string) {
  const r = await fetch(`${BASE}/api/batch?lang=${curLang()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ csv, title }),
  });
  if (r.ok) return (await r.json()) as { job_id: string; rows: number; errors: BatchRowError[] };
  let rowErrors: BatchRowError[] = [];
  try {
    const d = await r.clone().json();
    rowErrors = d?.detail?.errors ?? [];
  } catch { /* ignore */ }
  const e = new Error(await errMessage(r, "Không gửi được lô thẩm định")) as Error & { rowErrors?: BatchRowError[] };
  e.rowErrors = rowErrors;
  throw e;
}

export function getBatch(id: string) {
  return authed<BatchState>(`/api/batch/${encodeURIComponent(id)}`, {}, "Không tải được lần thẩm định");
}

export function listBatches() {
  return authed<{ max_rows: number; active: { id: string; state: string; progress?: BatchState["progress"] } | null; runs: BatchRunInfo[] }>(
    "/api/batch", {}, "Không tải được lịch sử thẩm định");
}

export function deleteBatch(id: string) {
  return authed<void>(`/api/batch/${encodeURIComponent(id)}`, { method: "DELETE" }, "Không xoá được");
}

export async function downloadBatchCsv(id: string) {
  const r = await fetch(`${BASE}/api/batch/${encodeURIComponent(id)}/csv`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await errMessage(r, "Không tải được CSV"));
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = `terratwin-tham-dinh-${id.slice(0, 8)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- HỒ SƠ VƯỜN CHUẨN EUDR: ranh thửa chuẩn GeoJSON EU + sàng lọc phá rừng sau 31/12/2020 ----
export type GeoGeometry = { type: "Point" | "MultiPoint" | "Polygon" | "MultiPolygon"; coordinates: unknown };
export type EudrIssue = { code: string; level: "error" | "warning" | "fixed"; message: string; other?: string; line?: number };
export type EudrPlot = {
  index: number; ref: string; src: string | null; producer: string | null; country: string | null;
  area_declared_ha: number | null; kind: "point" | "polygon" | null; geometry: GeoGeometry | null;
  area_ha: number | null; area_source: "polygon" | "declared" | "eu_default" | null;
  centroid: { lat: number; lon: number } | null; bbox: number[] | null; n_vertices: number;
  issues: EudrIssue[]; valid: boolean;
};
export type EudrValidation = {
  format: string; file_errors: EudrIssue[]; plots: EudrPlot[];
  summary: { n: number; n_valid: number; n_errors: number; n_warnings: number; n_fixed: number;
             n_polygons: number; n_points: number; total_ha: number; by_code: Record<string, number>;
             eu_ready: boolean; headline: string };
};
export type EudrLevel = "low" | "review" | "high" | "unknown";
export type EudrMap = { id: string; name: string; collection: string; res_m: number; pct: number | null;
                        pixels?: number; items?: string[]; buffered_m?: number; years?: number[] };
export type EudrS2 = { item: string; date: string; clear_pct: number; ndvi_mean: number;
                       processing_baseline: string | null; image: { url: string; bbox: number[] } } | null;
export type EudrScreening = {
  method: string; cutoff: string; computed_at: string; level: EudrLevel; label: string; reasons: string[];
  plot: { area_ha: number | null; kind: string | null; geometry_used: "polygon" | "circle_from_point";
          centroid: { lat: number; lon: number } | null };
  forest_2020: EudrMap[];
  wc2021: (EudrMap & { pct: number }) | null;
  io_trajectory: { year: number; tree_pct: number | null; item?: string | null }[];
  s2: { before: EudrS2; after: EudrS2; windows?: { before: string[]; after: string[] } };
  protected: { checked: boolean; inside: string[]; source?: string };
  signals: { votes?: string[]; strong?: string[]; io_before_pct?: number | null; io_after_pct?: number | null;
             io_drop_pts?: number | null; ndvi_drop?: number | null; loss?: boolean; loss_by?: string[] };
  thresholds: Record<string, number>;
  caveats: string[];
  dossier_id?: string;
};
export type EudrDossierFacts = {
  schema: string; kind: "eudr_plot"; lang: string;
  plot: { ref: string; producer: string | null; country: string; commodity: string | null; commodity_label: string | null;
          kind: "point" | "polygon"; geometry: GeoGeometry; area_ha: number; area_source: string;
          centroid: { lat: number; lon: number }; n_vertices: number };
  eu_format: { valid: boolean; issues: EudrIssue[]; rules: string };
  screening: EudrScreening;
  evidence_classes: Record<string, string>;
  predictions_included: boolean;
  sources: string[]; reproduce: string; disclaimer: string;
  disclosure?: { scheme: string; fields: Record<string, string> };
  land_document?: { fields: LandDocFields; checks: { id: string; ok: boolean | null; label: string }[];
                    verdict: "ok" | "review" | "red_flag"; label: string; image_sha256: string | null; source: string };
};
export type EudrMethod = {
  rule_version: string; cutoff: string; thresholds: Record<string, number>; sources: string[];
  levels: Record<EudrLevel, string>;
  eu_rules: { min_decimals: number; point_max_ha: number; default_point_ha: number; max_file_mb: number };
  max_screen_per_set: number;
  validation: { run_at: string; rule_version: string; n: number; metrics: Record<string, number | null>;
                pass_thresholds: Record<string, number>; passed: boolean;
                counts: Record<string, Record<EudrLevel, number>> } | null;
  validation_protocol: { registered: string; reference: string; sets: Record<string, { criteria: string; expected: string }>;
                         pass_thresholds: Record<string, number>; per_set: number; region: { note: string } } | null;
  validation_history?: {
    rule_version: string; sample: string; n: number; run_at?: string; passed: boolean;
    metrics: Record<string, number | null>; metrics_v1_same_sample?: Record<string, number | null>;
    pass_thresholds?: Record<string, number>; decision: string | null;
    by_region?: Record<string, Record<string, { n: number; ok_v2: number }>>;
    post_hoc_diagnosis: { label: string; finding: string; next_step: string;
                          never_forest_not_low: number; of_which_all_3_maps_ge_50pct_2020: number } | null;
  }[];
};
export type EudrPlotInput = { geometry: GeoGeometry; ref?: string; producer?: string; area_ha?: number | null;
                              gps_accuracy_m?: number | null };

export function eudrValidate(text: string, filename = "") {
  return postJson<EudrValidation>(`/api/eudr/validate?lang=${curLang()}`, { text, filename },
    "Không kiểm được tệp ranh thửa");
}

export function eudrScreen(p: EudrPlotInput) {
  return postJson<{ plot: EudrPlot; screening: EudrScreening | null }>(`/api/eudr/screen?lang=${curLang()}`, p,
    "Không sàng lọc được thửa này");
}

export function eudrMethod() {
  return getJson<EudrMethod>(`/api/eudr/method?lang=${curLang()}`, "Không tải được phương pháp");
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export async function eudrExport(body: { text?: string; filename?: string; geometry?: GeoGeometry; ref?: string;
                                         producer?: string; area_ha?: number | null }) {
  const r = await fetch(`${BASE}/api/eudr/export?lang=${curLang()}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không xuất được tệp GeoJSON"));
  saveBlob(await r.blob(), "terratwin-eudr.geojson");
}

export async function eudrIssueDossier(p: EudrPlotInput & { commodity: string; evidence_ids?: string[];
                                                              hide_producer?: boolean; land_document?: LandDocInput | null }) {
  const r = await fetch(`${BASE}/api/eudr/dossier?lang=${curLang()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(p),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không phát hành được hồ sơ vườn"));
  return (await r.json()) as Dossier;
}

export type EudrSetInfo = { id: string; title: string; commodity: string; n_plots: number; state: string;
                            created_at: string; headline: string | null;
                            progress: { done: number; total: number; current: string; phase: string } | null };
export type EudrSetSummary = { n: number; n_valid: number; n_invalid: number; n_screened: number;
                               by_level: Record<EudrLevel, number>; ha_by_level: Record<EudrLevel, number>;
                               headline: string; flagged: number };
export type EudrSet = {
  id: string; state: "queued" | "running" | "done"; title: string; commodity: string; producer: string;
  created_at: string; plots: EudrPlot[]; results: Record<string, EudrScreening>; summary: EudrSetSummary;
  progress?: { done: number; total: number; current: string; phase: string }; error?: string;
};

export async function eudrSubmitSet(body: { text: string; filename: string; title: string; commodity: string;
                                            producer: string }) {
  const r = await fetch(`${BASE}/api/eudr/sets?lang=${curLang()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await errMessage(r, "Không gửi được lô thửa"));
  return (await r.json()) as { set_id: string; screening: number; warning: string | null };
}

export function eudrListSets() {
  return authed<{ max_screen: number; sets: EudrSetInfo[] }>("/api/eudr/sets", {}, "Không tải được các lô thửa");
}

export function eudrGetSet(id: string) {
  return authed<EudrSet>(`/api/eudr/sets/${encodeURIComponent(id)}?lang=${curLang()}`, {}, "Không tải được lô thửa");
}

export function eudrDeleteSet(id: string) {
  return authed<void>(`/api/eudr/sets/${encodeURIComponent(id)}`, { method: "DELETE" }, "Không xoá được");
}

export function eudrSetDossiers(id: string) {
  return authed<{ n: number; issued: { ref: string; id: string; url: string }[] }>(
    `/api/eudr/sets/${encodeURIComponent(id)}/dossiers?lang=${curLang()}`, { method: "POST" },
    "Không phát hành được hồ sơ");
}

export async function eudrDownloadSet(id: string, what: "csv" | "geojson-valid" | "geojson-passed") {
  const path = what === "csv" ? `csv?lang=${curLang()}`
    : `geojson?which=${what === "geojson-passed" ? "passed" : "valid"}`;
  const r = await fetch(`${BASE}/api/eudr/sets/${encodeURIComponent(id)}/${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await errMessage(r, "Không tải được tệp"));
  saveBlob(await r.blob(), `terratwin-eudr-${id.slice(0, 8)}-${what}.${what === "csv" ? "csv" : "geojson"}`);
}

// ---- HẠ TẦNG NIỀM TIN ĐỢT 3: sổ đỏ, trợ lý EUDR, lô hàng + chứng thư Merkle, sổ minh bạch ----
export type LandDocFields = {
  so_thua?: string | null; to_ban_do?: string | null; dien_tich_m2?: number | string | null; ma_muc_dich?: string | null;
  muc_dich?: string | null; thoi_han?: string | null; dia_chi_thua?: string | null; so_phat_hanh?: string | null;
  ten_chu?: string | null; confidence?: number | null;
};
export type LandDocCheck = { fields: LandDocFields; checks: { id: string; ok: boolean | null; label: string }[];
                             verdict: "ok" | "review" | "red_flag"; label: string };
export type LandDocInput = { fields: LandDocFields; image_sha256?: string | null; source?: string };

export async function landdocExtract(file: File) {
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  const media = /png$/i.test(file.type) ? "image/png" : /webp$/i.test(file.type) ? "image/webp" : "image/jpeg";
  const r = await fetch(`${BASE}/api/landdoc/extract?lang=${curLang()}`, {
    method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ data_b64: btoa(bin), media_type: media }),
  });
  if (r.ok) return (await r.json()) as { fields: LandDocFields; image_sha256: string; source: string };
  let sha: string | undefined;
  try { sha = (await r.clone().json())?.detail?.image_sha256; } catch { /* bỏ qua */ }
  const e = new Error(await errMessage(r, "Không đọc được ảnh sổ")) as Error & { imageSha256?: string };
  e.imageSha256 = sha;
  throw e;
}

export function landdocCheck(fields: LandDocFields, areaHa: number | null, producer: string) {
  return postJson<LandDocCheck>(`/api/landdoc/check?lang=${curLang()}`, { fields, area_ha: areaHa ?? undefined, producer },
    "Không đối chiếu được giấy tờ");
}

export type AskCitation = { id: string; title: string; source: string; url: string; text: string; score: number; coverage: number };
export function eudrAsk(q: string) {
  return postJson<{ mode: "llm" | "extractive" | "none"; answer: string; citations: AskCitation[] }>(
    `/api/eudr/ask?lang=${curLang()}`, { q }, "Không hỏi được trợ lý");
}

export type LotDelivery = { dossier_id: string; kg: number; date?: string | null; review_ack?: string | null; entry_hash?: string };
export type LotCheckRow = { dossier_id: string; kg: number; status: "ok" | "warning" | "blocked"; notes: string[]; ref?: string;
                            area_ha?: number; level?: string; issued_at?: string; cap_kg?: number; season_kg?: number; other_lots_kg?: number };
export type LotChecks = { rows: LotCheckRow[]; n: number; n_blocked: number; n_warning: number; quantity_kg: number;
                          area_ha: number; by_level: Record<string, number>; certifiable: boolean; headline: string };
export type Lot = { id: string; ref: string; commodity: string; season: string; operator: string; state: "draft" | "certified";
                    certificate_id: string | null; certificate_url: string | null; created_at: string;
                    deliveries: LotDelivery[]; checks: LotChecks; errors?: string[] };
export type LotIn = { ref: string; commodity: string; season: string; operator: string; deliveries: LotDelivery[] };

export function lotsList() { return authed<{ lots: Lot[] }>("/api/lots", {}, "Không tải được lô hàng"); }
export function lotGet(id: string) { return authed<Lot>(`/api/lots/${encodeURIComponent(id)}`, {}, "Không tải được lô hàng"); }
export function lotCreate(b: LotIn) {
  return authed<Lot>(`/api/lots?lang=${curLang()}`, { method: "POST", body: JSON.stringify(b) }, "Không tạo được lô hàng");
}
export function lotUpdate(id: string, b: LotIn) {
  return authed<Lot>(`/api/lots/${encodeURIComponent(id)}?lang=${curLang()}`, { method: "PUT", body: JSON.stringify(b) },
    "Không cập nhật được lô hàng");
}
export function lotCertify(id: string) {
  return authed<{ lot: Lot; certificate: Dossier }>(`/api/lots/${encodeURIComponent(id)}/certify?lang=${curLang()}`,
    { method: "POST" }, "Không phát hành được chứng thư");
}
export function lotDelete(id: string) { return authed<void>(`/api/lots/${encodeURIComponent(id)}`, { method: "DELETE" }, "Không xoá được"); }
export function lotFromSet(setId: string) {
  return authed<{ commodity: string; operator: string; ref: string; rows: { dossier_id: string; ref: string; level: string; area_ha: number }[] }>(
    `/api/lots/from-set/${encodeURIComponent(setId)}?lang=${curLang()}`, { method: "POST" }, "Không lấy được lô thửa");
}
export async function lotDownload(id: string, what: "dds" | "geojson") {
  const r = await fetch(`${BASE}/api/lots/${encodeURIComponent(id)}/${what === "dds" ? `dds?lang=${curLang()}` : "geojson"}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(await errMessage(r, "Không tải được tệp"));
  const blob = what === "dds" ? new Blob([JSON.stringify(await r.json(), null, 2)], { type: "application/json" }) : await r.blob();
  saveBlob(blob, `terratwin-lo-${id}-${what === "dds" ? "dds-nhap.json" : "vi-tri.geojson"}`);
}
export type LotProof = { lot_certificate: string; leaf: { dossier_id: string; entry_hash: string; kg: number }; leaf_data: string;
                         leaf_index: number; tree_size: number; root: string; proof: string[] };
export function lotProof(certId: string, dossierId: string) {
  return getJson<LotProof>(`/api/lot-proof/${encodeURIComponent(certId)}/${encodeURIComponent(dossierId)}?lang=${curLang()}`,
    "Không lấy được bằng chứng thuộc lô");
}
export function dossierDisclosure(id: string) {
  return authed<{ token: string; url: string }>(`/api/dossier/${encodeURIComponent(id)}/disclosure`, {}, "Không lấy được đường link đầy đủ");
}
export type LotCertificateFacts = {
  schema: string; kind: "lot_certificate";
  lot: { ref: string; commodity: string; commodity_label: string; hs_code: string; hs_description: string; season: string;
         operator: string; quantity_kg: number; n_plots: number; area_ha: number; country_of_production: string };
  merkle: { algorithm: string; root: string; size: number; leaf: string };
  mass_balance: { yield_cap_t_ha: number | null; rule: string };
  checks: { by_level: Record<string, number>; n_warning: number; n_blocked: number };
  disclaimer: string;
};

export type FocRun = { date: string; chosen?: string; status: "accepted" | "rejected"; val?: Record<string, number>;
                       test: { balanced_accuracy: number; forest_recall: number; tree_crop_recall?: number; n?: number };
                       pass_thresholds?: Record<string, number>; n?: Record<string, number> };
// ---------- Lịch sử nước nhìn xuyên mây (radar Sentinel-1) ----------
export type WaterEvent = { start: string; end: string; n_scenes: number; dates: string[]; peak_cover: string; min_p50_db: number };
export type WaterHistoryResult = { available: boolean; message?: string; n_scenes: number; first: string; last: string;
  track: { orbit: string; relative_orbit: number; collection: string }; events: WaterEvent[]; n_events: number;
  baseline_db: Record<string, number>; series: [string, number, number][]; method: string; limits: string; computed: string };
export type WaterJob = { state: "queued" | "running" | "done" | "error"; job_id?: string; id?: string;
  progress?: { done: number; total: number }; result?: WaterHistoryResult; message?: string };
export function waterStatus() {
  return getJson<{ enabled: boolean; gate: { passed: boolean; run_at: string | null } }>(`/api/water/status?lang=${curLang()}`,
    "Không tải được trạng thái lịch sử nước");
}
export function waterStart(lat: number, lon: number) {
  return postJson<WaterJob>(`/api/water/history?lang=${curLang()}`, { lat, lon }, "Không bắt đầu được lịch sử nước");
}
export function waterPoll(jobId: string) {
  return getJson<WaterJob>(`/api/water/history/${encodeURIComponent(jobId)}`, "Không hỏi được tiến độ");
}

export type AefRun = { date: string; status: "accepted" | "rejected"; lambda?: number;
  test: { balanced_accuracy: number; forest_recall: number; tree_crop_recall?: number; n?: number };
  n?: Record<string, number>; comparator_s2_test?: { balanced_accuracy: number; forest_recall: number } };
export type AefStatus = { available: boolean; message?: string; runs: AefRun[]; attribution: string; source: string;
  protocol: { registered: string; h1_weak_labels: { pass: Record<string, number> } } };
export type AefPredict = { available: boolean; probability_forest: number | null; pixels?: number; message?: string;
  label?: string; attribution: string; model?: { kind: string; date: string; test: AefRun["test"] };
  change?: { cosine_2020_2025: number; status: "experimental"; label: string } | null };
export function eudrAefStatus() {
  return getJson<AefStatus>(`/api/eudr/ai/aef/status?lang=${curLang()}`, "Không tải được trạng thái AlphaEarth");
}
export function eudrAefPredict(geometry: GeoGeometry) {
  return postJson<AefPredict>(`/api/eudr/ai/aef?lang=${curLang()}`, { geometry }, "Không đọc được AlphaEarth");
}

export function eudrAiStatus() {
  return getJson<{ available: boolean; message?: string; runs: FocRun[]; kind?: string }>(`/api/eudr/ai/status?lang=${curLang()}`,
    "Không tải được trạng thái mô hình");
}

export type PendingDelivery = { lot_id: string; lot_ref: string; operator: string; season: string; commodity: string; kg: number;
                                date: string | null; lot_state: string; confirmation: { status: "confirmed" | "rejected"; at: string } | null };
export function dossierDeliveries(id: string, token: string) {
  return getJson<{ deliveries: PendingDelivery[] }>(`/api/dossier/${encodeURIComponent(id)}/deliveries?d=${encodeURIComponent(token)}&lang=${curLang()}`,
    "Không tải được các đợt giao hàng");
}
export function confirmDelivery(id: string, lotId: string, token: string, action: "confirm" | "reject") {
  return postJson<{ ok: boolean }>(`/api/dossier/${encodeURIComponent(id)}/deliveries/${encodeURIComponent(lotId)}?lang=${curLang()}`,
    { d: token, action }, "Không ghi được xác nhận");
}

export type EudrOverview = { plots: number; invalid: number; by_level: Record<EudrLevel, number>; ha_by_level: Record<EudrLevel, number>;
                             dossiers: number; lots: number; lots_certified: number; kg_certified: number;
                             deliveries_pending_confirmation: number;
                             attention: { set: string; ref: string; level: EudrLevel; dossier_id: string | null }[] };
export function eudrOverview() { return authed<EudrOverview>(`/api/eudr/overview?lang=${curLang()}`, {}, "Không tải được tổng quan"); }
export function eudrPublicStats() {
  return getJson<{ log_size: number; plot_dossiers: number; lot_certificates: number }>("/api/eudr/public-stats", "Không tải được số liệu");
}

export type TodayItem = { kind: string; priority: "urgent" | "action" | "info"; title: string; body: string; link: string };
export type Today = { date: string; deadlines: { date: string; days: number; who: string }[];
                      tip: { id: string; title: string; text: string; source: string; url: string } | null;
                      log_size: number; items: TodayItem[]; signed_in: boolean;
                      counts?: { plots_saved: number; dossiers: number; eudr_dossiers: number };
                      readiness?: Readiness | null };
export type ReadinessStep = { key: string; label: string; n: number; of: number; pct: number | null };
export type Readiness = { steps: ReadinessStep[]; levels: Record<string, { n: number; label: string }>;
                          eudr_dossiers: number; note: string };
export function getToday() { return getJson<Today>(`/api/today?lang=${curLang()}`, "Không tải được bảng tin"); }

// ── IoT ký số: thiết bị là khoá Ed25519, mọi số đo mang chữ ký kiểm được ──────────
export type IotDevice = {
  id: string; name: string; kind: "sensor" | "simulator"; public_key: string;
  lat: number | null; lon: number | null; dossier_id: string | null; revoked: boolean;
  created_at: string; last_seen: string | null; last_seq: number;
  latest: { measured_at: string; metrics: Record<string, number> } | null;
};
export type IotSeries = {
  device: IotDevice;
  series: ({ t: string } & Record<string, number | string>)[];
  catalog: Record<string, { unit: string; label: string }>;
};
export function iotDevices() {
  return authed<{ devices: IotDevice[] }>(`/api/iot/devices?lang=${curLang()}`, { method: "GET" }, "Không tải được thiết bị");
}
export function iotRegister(body: { name: string; public_key: string; kind: "sensor" | "simulator"; dossier_id?: string | null }) {
  return authed<IotDevice>(`/api/iot/devices?lang=${curLang()}`, { method: "POST", body: JSON.stringify(body) }, "Không đăng ký được thiết bị");
}
export function iotRevoke(id: string) {
  return authed<{ id: string; revoked: boolean }>(`/api/iot/devices/${id}`, { method: "DELETE" }, "Không thu hồi được thiết bị");
}
export function iotReadings(id: string, hours = 168) {
  return authed<IotSeries>(`/api/iot/devices/${id}/readings?hours=${hours}&lang=${curLang()}`, { method: "GET" }, "Không tải được số đo");
}
export function iotExport(id: string) {
  return authed<Record<string, unknown>>(`/api/iot/devices/${id}/export`, { method: "GET" }, "Không xuất được số đo");
}

// AI "rừng hay vườn cây?" — THAM KHẢO, không vào hồ sơ ký; chỉ bật khi đã qua ngưỡng đặt trước.
export type ForestOrCrop = {
  available: boolean; probability_forest: number | null; label?: string; message?: string;
  evidence_class?: string;
  model?: { kind: string; date: string; test: { balanced_accuracy: number; forest_recall: number; tree_crop_recall: number; n: number } };
};
export function eudrForestOrCrop(geometry: GeoGeometry) {
  return postJson<ForestOrCrop>(`/api/eudr/ai/forest-or-crop?lang=${curLang()}`, { geometry }, "AI chưa trả lời được");
}
