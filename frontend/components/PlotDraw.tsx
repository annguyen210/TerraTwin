"use client";

/**
 * LẤY RANH VƯỜN — vẽ trên ảnh vệ tinh hoặc ĐI BỘ QUANH VƯỜN với GPS điện thoại.
 *
 * Đi bộ: ghi một điểm khi đã đi ≥ 3 m và độ chính xác GPS ≤ 25 m (điểm kém hơn bị
 * bỏ, không âm thầm làm méo ranh). Độ chính xác trung vị gửi kèm để máy chủ cảnh
 * báo khi ranh đo trong điều kiện GPS kém (dưới tán cây, trời mây dày).
 */

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Footprints, LocateFixed, PenLine, RotateCcw, Square, Trash2 } from "lucide-react";
import type { GeoGeometry } from "@/lib/api";
import { useLang } from "@/lib/i18n";

type Pt = [number, number];
const MIN_STEP_M = 3;
const MAX_ACC_M = 25;

export function ringAreaHa(ring: Pt[]): number {
  if (ring.length < 3) return 0;
  const R = 6371007.181, k = Math.PI / 180;
  const lon0 = ring.reduce((a, p) => a + p[0], 0) / ring.length;
  const xy = ring.map(([x, y]) => [R * (x - lon0) * k * Math.cos(y * k), R * y * k]);
  let s = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i], [x2, y2] = xy[(i + 1) % xy.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2 / 10000;
}

function distM(a: Pt, b: Pt) {
  const k = Math.PI / 180, R = 6371000;
  const dx = (b[0] - a[0]) * k * Math.cos(((a[1] + b[1]) / 2) * k) * R;
  const dy = (b[1] - a[1]) * k * R;
  return Math.hypot(dx, dy);
}

function median(xs: number[]) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

export default function PlotDraw({ initial, onChange }: {
  initial?: GeoGeometry | null;
  onChange: (g: { geometry: GeoGeometry | null; gpsAccuracy: number | null }) => void;
}) {
  const { t } = useLang();
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [pts, setPts] = useState<Pt[]>([]);
  const [mode, setMode] = useState<"draw" | "walk" | "idle">("draw");
  const [acc, setAcc] = useState<number[]>([]);
  const [lastAcc, setLastAcc] = useState<number | null>(null);
  const [gpsErr, setGpsErr] = useState<string | null>(null);
  const watch = useRef<number | null>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;

  // Bản đồ: ảnh vệ tinh ESRI (cùng nền với bản đồ chính, không cần khoá).
  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({
      container: box.current,
      style: {
        version: 8,
        sources: {
          sat: { type: "raster", tileSize: 256, maxzoom: 18,
                 tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
                 attribution: "Esri World Imagery" },
          plot: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
        },
        layers: [
          { id: "sat", type: "raster", source: "sat" },
          { id: "plot-fill", type: "fill", source: "plot", filter: ["==", ["geometry-type"], "Polygon"],
            paint: { "fill-color": "#ffd23f", "fill-opacity": 0.18 } },
          { id: "plot-line", type: "line", source: "plot", filter: ["!=", ["geometry-type"], "Point"],
            paint: { "line-color": "#ffd23f", "line-width": 2.5 } },
          { id: "plot-pts", type: "circle", source: "plot", filter: ["==", ["geometry-type"], "Point"],
            paint: { "circle-radius": 4, "circle-color": "#ffd23f", "circle-stroke-color": "#0b1218", "circle-stroke-width": 1.5 } },
        ],
      },
      center: [108.05, 12.68],          // Buôn Ma Thuột — vùng cà phê
      zoom: 14,
      maxZoom: 19,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("click", (e) => {
      if (modeRef.current !== "draw") return;
      setPts((p) => [...p, [Number(e.lngLat.lng.toFixed(7)), Number(e.lngLat.lat.toFixed(7))]]);
    });
    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // BẢN NHÁP OFFLINE: vườn trên đồi hay mất sóng, điện thoại hay tải lại trang. Điểm ranh
  // lưu vào máy sau mỗi lần đổi; mở lại trang là khôi phục, không phải đi lại từ đầu.
  const DRAFT = "terratwin_plot_draft_v1";
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    try {
      const d = JSON.parse(localStorage.getItem(DRAFT) || "null");
      if (d && Array.isArray(d.pts) && d.pts.length >= 1) {
        setPts(d.pts); setAcc(Array.isArray(d.acc) ? d.acc : []); setMode("idle"); setRestored(true);
      }
    } catch { /* bộ nhớ trình duyệt bị chặn — bỏ qua */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    try {
      if (pts.length) localStorage.setItem(DRAFT, JSON.stringify({ pts, acc, at: Date.now() }));
      else localStorage.removeItem(DRAFT);
    } catch { /* bỏ qua */ }
  }, [pts, acc]);

  // Thửa nhập từ tệp → hiện lên và bay tới.
  useEffect(() => {
    if (!initial || initial.type !== "Polygon") return;
    const ring = (initial.coordinates as number[][][])[0].map((p) => [p[0], p[1]] as Pt);
    const open = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]
      ? ring.slice(0, -1) : ring;
    setPts(open);
    setMode("idle");
  }, [initial]);

  // Vẽ lại lớp thửa + báo ra ngoài mỗi khi điểm đổi.
  useEffect(() => {
    const map = mapRef.current;
    const feats: GeoJSON.Feature[] = pts.map((p) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: p } }));
    if (pts.length >= 3) feats.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...pts, pts[0]]] } });
    else if (pts.length === 2) feats.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: pts } });
    const apply = () => (map?.getSource("plot") as maplibregl.GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: feats });
    if (map?.isStyleLoaded()) apply(); else map?.once("load", apply);
    onChange({
      geometry: pts.length >= 3 ? { type: "Polygon", coordinates: [[...pts, pts[0]]] } : null,
      gpsAccuracy: median(acc),
    });
    if (map && pts.length >= 3 && mode === "idle") {
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 60, maxZoom: 18, duration: 600 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pts, acc]);

  function stopWalk() {
    if (watch.current != null) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
  }
  useEffect(() => stopWalk, []);

  function startWalk() {
    setGpsErr(null);
    if (!("geolocation" in navigator)) { setGpsErr(t("Thiết bị không có GPS.", "This device has no GPS.")); return; }
    setPts([]); setAcc([]); setMode("walk");
    watch.current = navigator.geolocation.watchPosition((pos) => {
      const a = pos.coords.accuracy;
      setLastAcc(a);
      const p: Pt = [Number(pos.coords.longitude.toFixed(7)), Number(pos.coords.latitude.toFixed(7))];
      mapRef.current?.easeTo({ center: p, zoom: Math.max(mapRef.current.getZoom(), 17) });
      if (a > MAX_ACC_M) return;                       // điểm kém: bỏ, không làm méo ranh
      setPts((prev) => (prev.length && distM(prev[prev.length - 1], p) < MIN_STEP_M ? prev : [...prev, p]));
      setAcc((prev) => [...prev, a]);
    }, (e) => {
      setGpsErr(e.code === 1 ? t("Bạn chưa cho phép dùng vị trí.", "Location permission was denied.")
        : t("Không lấy được GPS — thử lại ngoài trời.", "Could not get GPS — try again outdoors."));
      stopWalk(); setMode("idle");
    }, { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 });
  }

  function locate() {
    navigator.geolocation?.getCurrentPosition((pos) =>
      mapRef.current?.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 17 }),
    () => setGpsErr(t("Không lấy được vị trí.", "Could not get your location.")), { enableHighAccuracy: true, timeout: 15000 });
  }

  const area = ringAreaHa(pts);
  return (
    <div className="eu-draw">
      <div className="eu-draw-tools">
        <button className={`bat-btn ${mode === "draw" ? "" : "ghost"}`} onClick={() => { stopWalk(); setMode("draw"); }}>
          <PenLine size={15} aria-hidden="true" className="ui-ic" /> {t("Vẽ trên ảnh vệ tinh", "Draw on satellite image")}
        </button>
        {mode !== "walk" ? (
          <button className="bat-btn ghost" onClick={startWalk}>
            <Footprints size={15} aria-hidden="true" className="ui-ic" /> {t("Đi bộ quanh vườn (GPS)", "Walk the boundary (GPS)")}
          </button>
        ) : (
          <button className="bat-btn" onClick={() => { stopWalk(); setMode("idle"); }}>
            <Square size={15} aria-hidden="true" className="ui-ic" /> {t("Dừng — chốt ranh", "Stop — close boundary")}
          </button>
        )}
        <button className="bat-btn ghost" onClick={locate} title={t("Tới vị trí của tôi", "Go to my location")}>
          <LocateFixed size={15} aria-hidden="true" className="ui-ic" /> {t("Vị trí của tôi", "My location")}
        </button>
        <button className="bat-btn ghost" disabled={!pts.length} onClick={() => setPts((p) => p.slice(0, -1))}>
          <RotateCcw size={15} aria-hidden="true" className="ui-ic" /> {t("Bỏ điểm cuối", "Undo")}
        </button>
        <button className="bat-btn ghost danger" disabled={!pts.length} onClick={() => { stopWalk(); setPts([]); setAcc([]); setMode("draw"); }}>
          <Trash2 size={15} aria-hidden="true" className="ui-ic" /> {t("Xoá", "Clear")}
        </button>
      </div>
      <div ref={box} className="eu-map" />
      <p className="eu-draw-status">
        {mode === "draw" && t("Bấm lần lượt các góc vườn trên ảnh, theo một vòng.", "Tap the plot corners in order, going round once.")}
        {mode === "walk" && t(`Đang ghi: đi chậm sát mép vườn. GPS hiện tại ±${lastAcc ? lastAcc.toFixed(0) : "?"} m (bỏ điểm kém hơn ±${MAX_ACC_M} m).`,
                              `Recording: walk slowly along the edge. GPS now ±${lastAcc ? lastAcc.toFixed(0) : "?"} m (points worse than ±${MAX_ACC_M} m are dropped).`)}
        {" "}<b>{pts.length}</b> {t("điểm", "points")}{pts.length >= 3 ? <> · <b>{area.toFixed(area < 1 ? 3 : 2)} ha</b></> : null}
        {acc.length > 0 && <> · {t("GPS trung vị", "median GPS")} ±{median(acc)!.toFixed(0)} m</>}
      </p>
      {restored && pts.length > 0 && <p className="doc-note">{t("Đã khôi phục bản nháp ranh lưu trên máy này (lưu tự động, kể cả khi mất sóng). Bấm “Xoá” để làm lại.",
        "Restored the boundary draft saved on this device (saved automatically, even offline). Press “Clear” to start over.")}</p>}
      {gpsErr && <p className="bat-err">{gpsErr}</p>}
    </div>
  );
}
