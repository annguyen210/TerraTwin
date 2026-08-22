"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import {
  assess,
  fetchMe,
  getModules,
  getTerraScore,
  getToken,
  type Assessment,
  type AuthUser,
  type ModuleInfo,
  type TerraScore,
} from "@/lib/api";
import type { HeatmapResult } from "@/lib/api";
import Account from "@/components/Account";
import Alerts from "@/components/Alerts";
import FieldMode from "@/components/FieldMode";
import Heatmap from "@/components/Heatmap";
import ResultsPanel from "@/components/ResultsPanel";
import Copilot from "@/components/Copilot";
import Backtest from "@/components/Backtest";
import Overview from "@/components/Overview";
import WhatIf from "@/components/WhatIf";
import Insights from "@/components/Insights";
import Portfolio from "@/components/Portfolio";
import TimeLapse from "@/components/TimeLapse";
import Genome from "@/components/Genome";
import DesignStudio from "@/components/DesignStudio";
import Knowledge from "@/components/Knowledge";
import Feedback from "@/components/Feedback";
import Mrv from "@/components/Mrv";
import Provenance from "@/components/Provenance";
import Workspace from "@/components/Workspace";

const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

// Sáu luồng "xem sâu" gắn với một thửa cụ thể. Gom vào một dãy nút thay vì đổ
// hết ra: mỗi cái tốn từ vài giây tới hai phút để chạy, mở tất cả cùng lúc vừa
// chậm vừa đốt hạn mức của các nguồn dữ liệu miễn phí.
const DEEP = [
  { id: "timelapse", icon: "⏳", label: "Tua 10 năm", flow: "C04 Time-Lapse" },
  { id: "genome", icon: "🧬", label: "Vùng giống", flow: "S04 Twin Genome" },
  { id: "design", icon: "🎨", label: "Trồng gì", flow: "U03 Design Studio" },
  { id: "knowledge", icon: "🤝", label: "Kinh nghiệm", flow: "U02 Marketplace" },
  { id: "mrv", icon: "🌲", label: "Carbon", flow: "C07 MRV" },
  { id: "provenance", icon: "📜", label: "Truy xuất", flow: "SUP-12 Chuỗi cung ứng" },
] as const;

const GROUPS: Record<string, string> = {
  A: "Nhóm A · Quang học",
  B: "Nhóm B · Radar & địa hình",
  C: "Nhóm C · Chỉ số",
  D: "Nhóm D · Hạ tầng & chuỗi",
};

function TerraBadge({ t }: { t: TerraScore }) {
  const color =
    t.grade === "A"
      ? "#2E9E67"
      : t.grade === "B"
        ? "#3aa0a0"
        : t.grade === "C"
          ? "#B07A2E"
          : "#C2412E";
  return (
    <div className="terra">
      <div className="terra-score" style={{ borderColor: color, color }}>
        <b>{t.score}</b>
        <span>/100</span>
      </div>
      <div className="terra-txt">
        <div className="terra-grade" style={{ color }}>
          TerraScore · Hạng {t.grade}
        </div>
        <div className="terra-sum">{t.summary}</div>
        {t.real_data_ratio != null && (
          <div className="terra-real">
            🛰️ {Math.round(t.real_data_ratio * 100)}% hiểm họa dùng dữ liệu thật
          </div>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [modules, setModules] = useState<ModuleInfo[]>([]);
  const [active, setActive] = useState("salinity");
  const [result, setResult] = useState<Assessment | null>(null);
  const [terra, setTerra] = useState<TerraScore | null>(null);
  const [coord, setCoord] = useState<{ lat: number; lon: number } | null>(null);
  const [area, setArea] = useState<number | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number; lon: number; key: number } | null>(null);
  const [tab, setTab] = useState<"detail" | "overview">("detail");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [heat, setHeat] = useState<HeatmapResult | null>(null);
  const [workspace, setWorkspace] = useState(false);
  // Cột phải hẹp nên KHÔNG đổ hết mọi luồng ra cùng lúc: mở đủ thứ một lúc thì
  // người dùng phải cuộn qua sáu bảng mới thấy được kết quả module đang xem.
  const [deep, setDeep] = useState<
    "none" | "timelapse" | "genome" | "design" | "knowledge" | "mrv" | "provenance"
  >("none");

  useEffect(() => {
    getModules()
      .then(setModules)
      .catch((e) => setErr(e.message));
  }, []);

  // Khôi phục phiên đăng nhập nếu token còn hiệu lực.
  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  const run = useCallback(
    async (moduleId: string, lat: number, lon: number, areaHa?: number) => {
      setLoading(true);
      setErr(null);
      try {
        const [a, t] = await Promise.all([
          assess(moduleId, lat, lon, areaHa),
          getTerraScore(lat, lon),
        ]);
        setResult(a);
        setTerra(t);
      } catch (e: any) {
        setErr(e.message);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const onPick = useCallback(
    (lat: number, lon: number, areaHa?: number) => {
      setCoord({ lat, lon });
      setArea(areaHa);
      run(active, lat, lon, areaHa);
    },
    [active, run],
  );

  function selectModule(id: string) {
    setActive(id);
    setTab("detail");
    if (coord) run(id, coord.lat, coord.lon, area);
  }

  const loadPlot = useCallback(
    (lat: number, lon: number) => {
      setCoord({ lat, lon });
      setArea(undefined);
      setFlyTo({ lat, lon, key: Date.now() });
      run(active, lat, lon, undefined);
    },
    [active, run],
  );

  const grouped: Record<string, ModuleInfo[]> = {};
  for (const m of modules) (grouped[m.group] ??= []).push(m);

  return (
    <main className="app">
      <aside className="sidebar">
        <div className="brand">◵ TerraTwin</div>
        <p className="tag">
          Chọn mô-đun, <b>bấm bản đồ</b> (1 điểm hoặc vẽ vùng) rồi <b>Phân tích</b>.
        </p>
        {Object.keys(grouped)
          .sort()
          .map((g) => (
            <div key={g} className="group">
              <div className="ghead">{GROUPS[g] ?? g}</div>
              {grouped[g].map((m) => (
                <button
                  key={m.id}
                  className={`mod ${m.id === active ? "on" : ""}`}
                  onClick={() => selectModule(m.id)}
                >
                  <span className="ic">{m.icon}</span>
                  <span className="nm">{m.name}</span>
                </button>
              ))}
            </div>
          ))}
        <Account user={user} onAuth={setUser} />
        <Alerts user={user} />
        <Portfolio
          user={user}
          coord={coord}
          area={area}
          terra={terra}
          onLoad={loadPlot}
        />
        <button className="ws-open" onClick={() => setWorkspace(true)}>
          ⚙️ Khu làm việc
          <small>Twin đã lưu · dữ liệu · kênh cảnh báo · khoá API · vòng học</small>
        </button>

        <p className="foot">
          {modules.length} mũi nhọn · 12/12 ngành · dữ liệu thật: Open-Meteo ·
          NASA POWER · OpenStreetMap · Sentinel-2
        </p>
      </aside>

      <section className="mapwrap">
        <MapView onPick={onPick} flyTo={flyTo} heat={heat} />
      </section>

      <aside className="results">
        {loading && <p className="hint">Đang phân tích…</p>}
        {err && (
          <p className="err">
            {err.includes("Việt Nam") ? "🗺️ " : "⚠️ "}
            {err}
            {!err.includes("Việt Nam") && (
              <>
                <br />
                <small>Backend đã chạy chưa? (http://localhost:8000)</small>
              </>
            )}
          </p>
        )}
        {!loading && !err && !result && (
          <p className="hint">Bấm bản đồ (1 điểm hoặc vẽ vùng) → Phân tích.</p>
        )}
        {area != null && (
          <p className="areanote">📐 Diện tích vùng: {area} ha</p>
        )}
        {terra && <TerraBadge t={terra} />}

        {coord && (
          <div className="tabs">
            <button
              className={tab === "detail" ? "on" : ""}
              onClick={() => setTab("detail")}
            >
              Chi tiết module
            </button>
            <button
              className={tab === "overview" ? "on" : ""}
              onClick={() => setTab("overview")}
            >
              Toàn cảnh 14 module
            </button>
          </div>
        )}

        {coord && tab === "overview" && (
          <Overview
            lat={coord.lat}
            lon={coord.lon}
            area={area}
            onSelectModule={selectModule}
          />
        )}

        {tab === "detail" && (
          <>
            {result && <ResultsPanel a={result} />}
            {coord && result && (
              <WhatIf moduleId={active} lat={coord.lat} lon={coord.lon} />
            )}
            {coord && result && (
              <FieldMode moduleId={active} lat={coord.lat} lon={coord.lon} />
            )}
            {coord && result && (
              <Heatmap
                moduleId={active}
                lat={coord.lat}
                lon={coord.lon}
                onResult={setHeat}
              />
            )}
            {coord && result && (
              <Insights moduleId={active} lat={coord.lat} lon={coord.lon} />
            )}

            {coord && result && (
              <Feedback
                moduleId={active}
                moduleName={result.module_name}
                recommendation={result.recommendation}
                lat={coord.lat}
                lon={coord.lon}
                user={user}
              />
            )}

            {coord && result && (
              <div className="deep">
                <div className="deep-h">Xem sâu hơn về thửa này</div>
                <div className="deep-tabs">
                  {DEEP.map((d) => (
                    <button
                      key={d.id}
                      className={deep === d.id ? "on" : ""}
                      onClick={() => setDeep(deep === d.id ? "none" : d.id)}
                      title={d.flow}
                    >
                      {d.icon} {d.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {coord && deep === "timelapse" && (
              <TimeLapse moduleId={active} lat={coord.lat} lon={coord.lon} />
            )}
            {coord && deep === "genome" && (
              <Genome lat={coord.lat} lon={coord.lon} />
            )}
            {coord && deep === "design" && (
              <DesignStudio lat={coord.lat} lon={coord.lon} />
            )}
            {coord && deep === "knowledge" && (
              <Knowledge lat={coord.lat} lon={coord.lon} user={user} />
            )}
            {coord && deep === "mrv" && <Mrv lat={coord.lat} lon={coord.lon} />}
            {coord && deep === "provenance" && (
              <Provenance lat={coord.lat} lon={coord.lon} />
            )}

            {coord && <Copilot lat={coord.lat} lon={coord.lon} />}
          </>
        )}

        <Backtest />
      </aside>

      {workspace && (
        <Workspace
          user={user}
          coord={coord}
          area={area}
          onClose={() => setWorkspace(false)}
          onOpenPlot={(lat, lon) => {
            setWorkspace(false);
            loadPlot(lat, lon);
          }}
        />
      )}
    </main>
  );
}
