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
  danger: boolean;
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
  lead_days?: number | null;
  success?: boolean;
  verdict?: string;
  peak?: BacktestPoint;
  first_danger?: BacktestPoint | null;
  series?: BacktestPoint[];
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
