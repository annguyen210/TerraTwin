"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useLang } from "@/lib/i18n";
import { autoBoundary } from "@/lib/api";

type Pt = [number, number]; // [lng, lat]

// A8 — cờ tắt cứng. Xem chú thích ở nút "Tự vẽ ranh thửa" bên dưới.
const AUTO_BOUNDARY_READY = false;

function areaHa(pts: Pt[]): number {
  if (pts.length < 3) return 0;
  const latMean = (pts.reduce((s, p) => s + p[1], 0) / pts.length) * (Math.PI / 180);
  const mLat = 111320;
  const mLon = 111320 * Math.cos(latMean);
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    a += x1 * mLon * (y2 * mLat) - x2 * mLon * (y1 * mLat);
  }
  return Math.abs(a / 2) / 10000;
}

function centroid(pts: Pt[]): Pt {
  const n = pts.length;
  return [
    pts.reduce((s, p) => s + p[0], 0) / n,
    pts.reduce((s, p) => s + p[1], 0) / n,
  ];
}

type Heat = {
  cells: { lat: number; lon: number; value: number | null; risk: string }[];
  cell_dlat: number;
  cell_dlon: number;
} | null;

const RISK_FILL: Record<string, string> = {
  safe: "#2E9E67",
  warning: "#B07A2E",
  danger: "#C2412E",
  unknown: "#5a6b73",
};

export default function MapView({
  onPick,
  flyTo,
  heat,
  plot,
}: {
  onPick: (lat: number, lon: number, areaHa?: number) => void;
  flyTo?: { lat: number; lon: number; key: number } | null;
  heat?: Heat;
  // Ô ĐANG PHÂN TÍCH. Trước đây bản đồ — thứ CHIẾM NHIỀU CHỖ NHẤT trên màn
  // hình — không phản ánh gì cả, kể cả sau khi đã quét xong: nó vẫn là một tấm
  // nền trơn. Người dùng nhìn vào phần lớn nhất của sản phẩm và thấy trống.
  // Khung này cho họ thấy ĐÚNG mảnh đất vừa được chấm, và màu viền nói luôn
  // mức rủi ro cao nhất tìm được.
  plot?: { lat: number; lon: number; spanM: number; risk: string } | null;
}) {
  const { t } = useLang();
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ptsRef = useRef<Pt[]>([]);
  const [count, setCount] = useState(0);
  const [autoDrawing, setAutoDrawing] = useState(false);   // A8
  const [autoMsg, setAutoMsg] = useState<string | null>(null);

  function refresh() {
    const map = mapRef.current;
    if (!map) return;
    const pts = ptsRef.current;
    const dpts = map.getSource("dpts") as maplibregl.GeoJSONSource | undefined;
    const dpoly = map.getSource("dpoly") as maplibregl.GeoJSONSource | undefined;
    dpts?.setData({
      type: "FeatureCollection",
      features: pts.map((p) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: p },
        properties: {},
      })),
    } as any);
    dpoly?.setData({
      type: "FeatureCollection",
      features:
        pts.length >= 3
          ? [
              {
                type: "Feature",
                geometry: { type: "Polygon", coordinates: [[...pts, pts[0]]] },
                properties: {},
              },
            ]
          : [],
    } as any);
    setCount(pts.length);
  }

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      // Nền ẢNH VỆ TINH THẬT (ESRI World Imagery) — thấy tận thửa đất, đúng thông
      // điệp "con mắt cắm vào đất Việt". Không cần API key.
      style: {
        version: 8,
        sources: {
          sat: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            // ESRI World Imagery chỉ có ảnh tới ~z18 ở phần lớn Việt Nam (nông
            // thôn/ruộng). Không đặt maxzoom thì zoom sâu hơn sẽ xin tile không
            // tồn tại → ESRI trả tile "Map data not yet available". Đặt maxzoom=18
            // để MapLibre PHÓNG TO tile thật z18 (hơi mờ nhưng là ảnh thật) thay
            // vì báo lỗi.
            maxzoom: 18,
            attribution: "Esri, Maxar, Earthstar Geographics",
          },
          labels: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            maxzoom: 18,
          },
        },
        layers: [
          { id: "sat", type: "raster", source: "sat" },
          { id: "labels", type: "raster", source: "labels" },
        ],
      },
      center: [106.3, 9.6],
      zoom: 7,
      // Cho phép zoom sâu hơn nguồn ảnh (overzoom): thấy sát thửa đất, ảnh mờ dần
      // nhưng KHÔNG bao giờ hiện tile lỗi.
      maxZoom: 19,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      // Lớp bản đồ nhiệt nằm DƯỚI các lớp vẽ tay để không che điểm người dùng chọn.
      map.addSource("plot", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "plot-line", type: "line", source: "plot",
        paint: { "line-color": ["get", "color"], "line-width": 2.5, "line-dasharray": [2, 1.5] },
      });
      map.addLayer({
        id: "plot-glow", type: "line", source: "plot",
        paint: { "line-color": ["get", "color"], "line-width": 9, "line-opacity": 0.16 },
      });
      map.addSource("heat", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "heat-fill",
        type: "fill",
        source: "heat",
        paint: { "fill-color": ["get", "color"], "fill-opacity": 0.45 },
      });
      map.addLayer({
        id: "heat-line",
        type: "line",
        source: "heat",
        paint: { "line-color": ["get", "color"], "line-width": 0.5, "line-opacity": 0.6 },
      });
      map.addSource("dpoly", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "dpoly-fill", type: "fill", source: "dpoly", paint: { "fill-color": "#5fcb8e", "fill-opacity": 0.25 } });
      map.addLayer({ id: "dpoly-line", type: "line", source: "dpoly", paint: { "line-color": "#5fcb8e", "line-width": 2 } });
      map.addSource("dpts", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "dpts-c", type: "circle", source: "dpts", paint: { "circle-radius": 5, "circle-color": "#2E9E67", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 } });
    });
    map.on("click", (e) => {
      ptsRef.current.push([e.lngLat.lng, e.lngLat.lat]);
      refresh();
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Vẽ lưới bản đồ nhiệt: mỗi ô là một ô vuông quanh tâm ô.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const draw = () => {
      const src = map.getSource("heat") as maplibregl.GeoJSONSource | undefined;
      if (!src) return;
      if (!heat || heat.cells.length === 0) {
        src.setData({ type: "FeatureCollection", features: [] } as any);
        return;
      }
      const hy = heat.cell_dlat / 2;
      const hx = heat.cell_dlon / 2;
      src.setData({
        type: "FeatureCollection",
        features: heat.cells.map((c) => ({
          type: "Feature",
          properties: {
            // Ô có thể tự chỉ định màu (dùng cho bản đồ NGÀY ĐẾN, nơi màu mã
            // hoá thời điểm chứ không phải mức độ). Không có thì về màu rủi ro.
            color: (c as { color?: string }).color
              ?? RISK_FILL[c.risk] ?? RISK_FILL.unknown,
            value: c.value ?? -1,
          },
          geometry: {
            type: "Polygon",
            coordinates: [[
              [c.lon - hx, c.lat - hy],
              [c.lon + hx, c.lat - hy],
              [c.lon + hx, c.lat + hy],
              [c.lon - hx, c.lat + hy],
              [c.lon - hx, c.lat - hy],
            ]],
          },
        })),
      } as any);
    };
    if (map.isStyleLoaded()) draw();
    else map.once("load", draw);
  }, [heat]);

  // Vẽ khung ô vừa phân tích.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("plot") as maplibregl.GeoJSONSource | undefined;
    if (!src) return;
    if (!plot) {
      src.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    const color =
      plot.risk === "danger" ? "#E2705C"
      : plot.risk === "warning" ? "#D8A253"
      : "#5CBF8B";
    const dy = plot.spanM / 2 / 111320;
    const dx = plot.spanM / 2 / (111320 * Math.max(0.2, Math.abs(Math.cos((plot.lat * Math.PI) / 180))));
    src.setData({
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        properties: { color },
        geometry: {
          type: "Polygon",
          coordinates: [[
            [plot.lon - dx, plot.lat - dy], [plot.lon + dx, plot.lat - dy],
            [plot.lon + dx, plot.lat + dy], [plot.lon - dx, plot.lat + dy],
            [plot.lon - dx, plot.lat - dy],
          ]],
        },
      }],
    });
  }, [plot]);

  // Bay tới nơi vừa tìm/vị trí — ZOOM SÂU tới mức thấy TỪNG THỬA (z16, ~0.6 m/px)
  // để người dùng nhận ra đúng thửa của mình, không dừng ở mức cả thị trấn.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyTo) return;
    map.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: 16 });
    // KHÔNG tự chấm điểm — để người dùng tự kéo ô ngắm vào đúng thửa rồi bấm.
    ptsRef.current = [];
    refresh();
  }, [flyTo?.key]);

  function analyze() {
    const pts = ptsRef.current;
    if (pts.length === 0) return;
    if (pts.length < 3) {
      onPick(pts[0][1], pts[0][0]);
      return;
    }
    const c = centroid(pts);
    onPick(c[1], c[0], Math.round(areaHa(pts) * 100) / 100);
  }

  // Phân tích ĐÚNG chỗ giữa ô ngắm ✛ — cách chính xác nhất để chấm thửa của mình:
  // kéo/zoom cho thửa vào giữa rồi bấm, khỏi phải chạm trúng một ô bé xíu.
  function analyzeCenter() {
    const map = mapRef.current;
    if (!map) return;
    const c = map.getCenter();
    ptsRef.current = [];
    refresh();
    onPick(c.lat, c.lng);
  }

  function clear() {
    ptsRef.current = [];
    refresh();
    setAutoMsg(null);
  }

  // A8 — gọi watershed tại tâm ô ngắm, vẽ ranh trả về lên bản đồ dưới dạng đa
  // giác THƯỜNG (cùng cơ chế với vẽ tay): nếu ranh sai, người dùng bấm "Xoá"
  // rồi tự vẽ lại bằng tay — không cần một cơ chế kéo-sửa riêng.
  async function autoDraw() {
    const map = mapRef.current;
    if (!map) return;
    const c = map.getCenter();
    setAutoDrawing(true);
    setAutoMsg(null);
    try {
      const r = await autoBoundary(c.lat, c.lng, 500);
      if (!r.available || !r.outline_rows || !r.bbox || !r.grid_size) {
        setAutoMsg(r.message);
        return;
      }
      const [lonMin, latMin, lonMax, latMax] = r.bbox;
      const g = r.grid_size;
      const rc = (row: number, col: number): Pt => [
        lonMin + ((col + 0.5) / g) * (lonMax - lonMin),
        latMax - ((row + 0.5) / g) * (latMax - latMin),
      ];
      const left = r.outline_rows.map(([row, cLeft]) => rc(row, cLeft));
      const right = r.outline_rows.slice().reverse().map(([row, , cRight]) => rc(row, cRight));
      ptsRef.current = [...left, ...right];
      refresh();
      setAutoMsg(r.message);
      if (r.area_ha != null) onPick(c.lat, c.lng, r.area_ha);
    } catch (e) {
      setAutoMsg((e as Error).message);
    } finally {
      setAutoDrawing(false);
    }
  }

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={ref} style={{ position: "absolute", inset: 0 }} />

      {/* Kính ngắm CỐ ĐỊNH giữa màn — người dùng kéo/zoom cho ĐÚNG thửa của mình
          vào giữa rồi bấm "Phân tích đúng chỗ này". Cách chấm chính xác nhất khi
          một tỉnh có hàng nghìn thửa. */}
      <div className="map-cross" aria-hidden>
        <span className="mc-v" /><span className="mc-h" /><span className="mc-o" />
      </div>

      <div className="drawbar">
        <span className="db-hint">
          {count === 0
            ? t("Kéo & zoom cho ĐÚNG thửa của bạn vào giữa ô ngắm ✛ — rồi bấm nút xanh",
                "Pan & zoom your exact plot into the ✛ crosshair — then tap the green button")
            : t(`${count} điểm${count >= 3 ? " · đã tạo vùng ruộng" : ""}`,
                `${count} point(s)${count >= 3 ? " · field area created" : ""}`)}
        </span>
        <button className="db-primary" onClick={analyzeCenter}>
          📍 {t("Phân tích đúng thửa ở giữa", "Analyze the plot at center")}
        </button>
        {/* A8 — TẠM ẨN. watershed_from_seed() luôn lan tới đúng trần an toàn
            MAX_AREA_PX_RATIO bất kể kích cỡ khung (đo thật: 500m→85.0ha,
            150m→7.65ha, 1000m→333.9ha — luôn = 0,85×khung) vì hàng đợi ưu
            tiên toàn cục rò qua nhiễu ảnh thật thay vì dừng ở bờ ruộng. Diện
            tích sai này từng chảy thẳng vào onPick() → lưu làm diện tích
            thửa. Chỉ bật lại sau khi watershed.py trả available:false đúng
            lúc chạm trần thay vì trả con số trần ra, và diện tích ổn định
            qua nhiều cỡ khung tại toạ độ ruộng thật (xem AUTO_BOUNDARY_READY
            bên dưới). */}
        {AUTO_BOUNDARY_READY && (
          <button onClick={autoDraw} disabled={autoDrawing}>
            {autoDrawing
              ? t("Đang tự vẽ ranh…", "Auto-drawing boundary…")
              : `🪄 ${t("Tự vẽ ranh thửa", "Auto-draw plot boundary")}`}
          </button>
        )}
        {count > 0 && (
          <>
            <button onClick={analyze}>{t("Phân tích điểm/vùng đã chấm", "Analyze marked point/area")}</button>
            <button onClick={clear} className="ghost">{t("Xóa", "Clear")}</button>
          </>
        )}
        {autoMsg && <span className="db-hint">{autoMsg}</span>}
      </div>
    </div>
  );
}
