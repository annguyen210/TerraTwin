"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type Pt = [number, number]; // [lng, lat]

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
}: {
  onPick: (lat: number, lon: number, areaHa?: number) => void;
  flyTo?: { lat: number; lon: number; key: number } | null;
  heat?: Heat;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const ptsRef = useRef<Pt[]>([]);
  const [count, setCount] = useState(0);

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
            attribution: "Ảnh: Esri, Maxar, Earthstar Geographics",
          },
          labels: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
          },
        },
        layers: [
          { id: "sat", type: "raster", source: "sat" },
          { id: "labels", type: "raster", source: "labels" },
        ],
      },
      center: [106.3, 9.6],
      zoom: 7,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      // Lớp bản đồ nhiệt nằm DƯỚI các lớp vẽ tay để không che điểm người dùng chọn.
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
            color: RISK_FILL[c.risk] ?? RISK_FILL.unknown,
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

  // Bay tới thửa đã lưu khi tải lại từ danh mục.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyTo) return;
    map.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: 12 });
    ptsRef.current = [[flyTo.lon, flyTo.lat]];
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

  function clear() {
    ptsRef.current = [];
    refresh();
  }

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div ref={ref} style={{ position: "absolute", inset: 0 }} />
      <div className="drawbar">
        <span>
          {count === 0
            ? "Bấm bản đồ: 1 điểm, hoặc nhiều điểm để vẽ vùng ruộng"
            : `${count} điểm${count >= 3 ? " · đã tạo vùng" : ""}`}
        </span>
        <button onClick={analyze} disabled={count === 0}>
          Phân tích
        </button>
        <button onClick={clear} className="ghost" disabled={count === 0}>
          Xóa
        </button>
      </div>
    </div>
  );
}
