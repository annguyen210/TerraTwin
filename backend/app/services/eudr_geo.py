"""RANH THỬA CHUẨN EUDR — đọc, kiểm và xuất toạ độ vườn đúng mẫu GeoJSON của EU.

VÌ SAO. Từ 30/12/2026 (doanh nghiệp lớn và vừa; 30/6/2027 doanh nghiệp nhỏ) mỗi
lô cà phê, cao su, gỗ… bán vào EU phải kèm toạ độ TỪNG THỬA sản xuất. Hệ thống
thông tin của EU (TRACES) nhận tệp GeoJSON và TỪ CHỐI những lỗi rất đời thường:
ranh chưa khép kín, ranh tự cắt hình số 8, đa giác có lỗ, đảo kinh độ với vĩ độ,
thửa trên 4 ha chỉ khai một điểm. Ở Việt Nam chỉ khoảng 10% hộ trồng cà phê có
dữ liệu đến từng thửa — phần lớn toạ độ sẽ được đo vội bằng điện thoại, gom qua
đại lý, dán vào Excel. Bắt lỗi TRƯỚC khi nộp rẻ hơn rất nhiều so với để lô hàng
bị giữ ở cảng.

QUY TẮC LẤY TỪ ĐÂU (không tự đặt ra):
  · Quy định (EU) 2023/1115 Điều 2(28): toạ độ dùng ÍT NHẤT 6 chữ số thập phân.
  · Điều 9(1)(d): thửa trên 4 ha (trừ chăn nuôi bò) phải khai bằng ĐA GIÁC.
  · Mô tả tệp GeoJSON của TRACES: chỉ nhận Point, MultiPoint, Polygon,
    MultiPolygon theo WGS84 (kinh độ, vĩ độ); điểm đầu và cuối của ranh trùng
    nhau; không nhận đa giác có lỗ, ranh cắt nhau, cạnh chồng nhau, ranh hở;
    điểm không khai Area thì EU mặc định 4 ha; toạ độ bị cắt còn 6 chữ số;
    tệp tối đa 25 MB mỗi tờ khai. Thuộc tính: ProducerName, ProducerCountry
    (mã ISO 2 chữ), ProductionPlace, Area (ha, cho điểm).

DIỆN TÍCH tính trên phép chiếu SIN (sinusoidal) — phép chiếu ĐỒNG DIỆN TÍCH trên
mặt cầu bán kính tương đương (authalic) của WGS84; sai khác với diện tích trắc
địa chính xác dưới 0,5% cho thửa nông hộ. Không cần pyproj.

KHÔNG làm thay người dùng những việc làm đổi ý nghĩa ranh: tự sửa chỉ khi kết quả
chắc chắn là ý người khai (khép ranh, bỏ điểm trùng liền nhau, đổi lại kinh/vĩ độ
bị đảo, xoay chiều ranh). Ranh tự cắt hay có lỗ thì báo lỗi kèm chỗ sai và cách
sửa — tự "nắn" là khai hộ người ta một mảnh đất khác.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import xml.etree.ElementTree as ET

from shapely.geometry import MultiPolygon, Point, Polygon, mapping
from shapely.geometry.polygon import orient
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from app.services.reqlang import tr

R_AUTHALIC = 6_371_007.181           # m — bán kính cầu cùng diện tích với elipxoit WGS84
EU_POINT_MAX_HA = 4.0                # Điều 9(1)(d)
EU_DEFAULT_POINT_HA = 4.0            # TRACES: điểm không khai Area → 4 ha
EU_MIN_DECIMALS = 6                  # Điều 2(28)
EU_MAX_FILE_BYTES = 25 * 1024 * 1024
EU_GEOM_TYPES = ("Point", "MultiPoint", "Polygon", "MultiPolygon")

# Ngưỡng cảnh báo — chỉ CẢNH BÁO (không phải lỗi EU), để người khai xem lại.
LOW_PRECISION_DECIMALS = 4           # mọi toạ độ ≤ 4 chữ số (~11 m) → gần như chắc đo thô
AREA_MISMATCH_PCT = 25.0             # diện tích khai lệch diện tích tính từ ranh
TINY_HA = 0.01                       # < 100 m²: thường là GPS nhảy hay nhầm đơn vị
HUGE_HA = 1000.0
SPIKE_DEG = 10.0                     # góc nhọn hơn mức này giữa hai cạnh dài = GPS nhảy
SPIKE_MIN_M = 15.0
OVERLAP_ERROR_PCT = 5.0              # hai thửa chồng nhau ≥ 5% thửa nhỏ hơn → lỗi
OVERLAP_WARN_PCT = 0.5               # 0,5–5%: thường là sai số GPS ở mép ranh
POINT_DUP_M = 5.0
GPS_ACCURACY_WARN_M = 15.0

# Lãnh thổ đất liền Việt Nam (hộp bao thô — cùng hộp với thẩm định hàng loạt).
VN_LAT = (8.0, 23.6)
VN_LON = (102.0, 110.0)

_ERR_BY_DECIMALS = {0: "111 km", 1: "11 km", 2: "1,1 km", 3: "110 m", 4: "11 m", 5: "1,1 m"}


def max_plots() -> int:
    try:
        return int(os.environ.get("TERRATWIN_EUDR_MAX_PLOTS_VALIDATE", "") or 5000)
    except ValueError:
        return 5000


# ------------------------------------------------------------------ số giữ chữ số

class _D(float):
    """Số thực nhớ SỐ CHỮ SỐ THẬP PHÂN như viết trong tệp gốc — EU đòi ≥ 6,
    mà float thì quên mất "106.5" và "106.500000" khác nhau ở đâu."""

    def __new__(cls, s):
        v = super().__new__(cls, s)
        st = str(s).strip().lower()
        if "e" in st:
            v.dec = None                      # dạng 1.2e-5: không suy ra được
        else:
            v.dec = len(st.split(".", 1)[1]) if "." in st else 0
        return v


def _dec(v) -> int | None:
    return getattr(v, "dec", None)


def _issue(code: str, level: str, vi: str, en: str, **extra) -> dict:
    """level: error (EU từ chối) · warning (nên xem lại) · fixed (đã tự sửa)."""
    return {"code": code, "level": level, "message": tr(vi, en), **extra}


# ------------------------------------------------------------------ phép chiếu

def _fwd(lon0: float):
    k = math.pi / 180.0

    def f(x, y, z=None):
        return R_AUTHALIC * (x - lon0) * k * math.cos(y * k), R_AUTHALIC * y * k
    return f


def _inv(lon0: float):
    k = math.pi / 180.0

    def f(x, y, z=None):
        lat = y / R_AUTHALIC / k
        c = math.cos(lat * k)
        return (lon0 + x / (R_AUTHALIC * k * c)) if c > 1e-12 else lon0, lat
    return f


def to_metric(geom, lon0: float):
    return transform(_fwd(lon0), geom)


def from_metric(geom, lon0: float):
    return transform(_inv(lon0), geom)


def area_ha(geom_lonlat, lon0: float | None = None) -> float:
    if lon0 is None:
        lon0 = geom_lonlat.centroid.x
    return to_metric(geom_lonlat, lon0).area / 10_000.0


# ------------------------------------------------------------------ đọc tệp

def detect_format(text: str, filename: str = "") -> str:
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext in ("geojson", "json"):
        return "geojson"
    if ext == "kml":
        return "kml"
    if ext in ("csv", "txt", "tsv"):
        return "csv"
    head = (text or "").lstrip("﻿").lstrip()[:200].lower()
    if head.startswith("{") or head.startswith("["):
        return "geojson"
    if head.startswith("<") and "kml" in (text or "")[:2000].lower():
        return "kml"
    return "csv"


def parse(text: str, filename: str = "") -> tuple[list[dict], list[dict], str]:
    """→ (thửa thô, lỗi cấp tệp, định dạng). Thửa thô: ref, name, producer,
    country, area_declared, geom (GeoJSON, số kiểu _D), src (vị trí trong tệp)."""
    text = (text or "").lstrip("﻿")
    fmt = detect_format(text, filename)
    if not text.strip():
        return [], [_issue("E_EMPTY", "error", "Tệp rỗng.", "Empty file.")], fmt
    if len(text.encode("utf-8")) > EU_MAX_FILE_BYTES:
        return [], [_issue("E_FILE_SIZE", "error",
                           "Tệp lớn hơn 25 MB — vượt trần một tờ khai của hệ thống EU. "
                           "Chia thành nhiều tệp.",
                           "File is larger than 25 MB — above the EU system's per-statement "
                           "limit. Split it into several files.")], fmt
    fn = {"geojson": _parse_geojson, "kml": _parse_kml, "csv": _parse_csv}[fmt]
    raws, errs = fn(text)
    if len(raws) > max_plots():
        errs.append(_issue("E_TOO_MANY", "error",
                           f"Tệp có {len(raws)} thửa — chỉ kiểm {max_plots()} thửa đầu.",
                           f"File has {len(raws)} plots — only the first {max_plots()} are checked."))
        raws = raws[:max_plots()]
    return raws, errs, fmt


def _first(props: dict, keys: tuple[str, ...]):
    low = {str(k).lower(): v for k, v in (props or {}).items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return v
    return None


def _to_float(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


_REF_KEYS = ("ProductionPlace", "ref", "ma", "mã", "id", "plot_id", "name", "ten", "tên")
_PRODUCER_KEYS = ("ProducerName", "producer", "chu_ho", "chủ_hộ", "ho_ten", "họ_tên", "farmer")
_AREA_KEYS = ("Area", "area_ha", "area", "dien_tich", "diện_tích", "ha")


def _raw_from_props(props: dict, geom, src: str, idx: int) -> dict:
    ref = _first(props, _REF_KEYS)
    return {
        "ref": str(ref if ref is not None else f"#{idx}").strip()[:80],
        "producer": (str(_first(props, _PRODUCER_KEYS)).strip()[:120]
                     if _first(props, _PRODUCER_KEYS) is not None else None),
        "country": (str(_first(props, ("ProducerCountry", "country"))).strip()[:2].upper()
                    if _first(props, ("ProducerCountry", "country")) is not None else None),
        "area_declared": _to_float(_first(props, _AREA_KEYS)),
        "gps_accuracy_m": _to_float(_first(props, ("gps_accuracy_m",))),
        "geom": geom, "src": src,
    }


def _parse_geojson(text: str) -> tuple[list[dict], list[dict]]:
    try:
        obj = json.loads(text, parse_float=_D, parse_int=_D)
    except json.JSONDecodeError as e:
        return [], [_issue("E_JSON", "error",
                           f"GeoJSON hỏng ở dòng {e.lineno}, cột {e.colno}: {e.msg}.",
                           f"Broken GeoJSON at line {e.lineno}, column {e.colno}: {e.msg}.")]
    if isinstance(obj, list):
        feats = obj
    elif isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
    elif isinstance(obj, dict) and obj.get("type") == "Feature":
        feats = [obj]
    elif isinstance(obj, dict) and obj.get("type") in EU_GEOM_TYPES + ("LineString", "MultiLineString",
                                                                        "GeometryCollection"):
        feats = [{"type": "Feature", "properties": {}, "geometry": obj}]
    else:
        return [], [_issue("E_GEOJSON_TYPE", "error",
                           "Không nhận ra cấu trúc GeoJSON (cần FeatureCollection, Feature hoặc hình học).",
                           "Unrecognised GeoJSON structure (need a FeatureCollection, Feature or geometry).")]
    raws, errs = [], []
    for i, f in enumerate(feats, 1):
        if not isinstance(f, dict):
            errs.append(_issue("E_FEATURE", "error", f"Phần tử #{i} không phải Feature.",
                               f"Element #{i} is not a Feature."))
            continue
        geom = f.get("geometry") if f.get("type") == "Feature" else f
        props = dict(f.get("properties") or {})
        if f.get("id") is not None and _first(props, _REF_KEYS) is None:
            props["id"] = f["id"]
        raws.append(_raw_from_props(props, geom, f"#{i}", i))
    return raws, errs


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _kml_coords(text: str) -> list[list]:
    out = []
    for tup in (text or "").split():
        parts = tup.split(",")
        if len(parts) >= 2:
            try:
                out.append([_D(parts[0]), _D(parts[1])])
            except ValueError:
                return []
    return out


def _parse_kml(text: str) -> tuple[list[dict], list[dict]]:
    # Từ chối DOCTYPE/ENTITY: chặn tấn công "bom XML" (billion laughs) ngay từ cửa.
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.IGNORECASE):
        return [], [_issue("E_KML_UNSAFE", "error",
                           "Tệp KML có khai báo DOCTYPE/ENTITY — từ chối vì lý do an toàn.",
                           "KML file declares DOCTYPE/ENTITY — rejected for safety.")]
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        return [], [_issue("E_KML", "error", f"KML hỏng: {e}.", f"Broken KML: {e}.")]
    raws = []
    for i, pm in enumerate((el for el in root.iter() if _local(el.tag) == "Placemark"), 1):
        name = next((c.text for c in pm if _local(c.tag) == "name" and c.text), None)
        polys, points, lines = [], [], 0
        for el in pm.iter():
            t = _local(el.tag)
            if t == "Polygon":
                rings = []
                for b in el:
                    bt = _local(b.tag)
                    if bt not in ("outerBoundaryIs", "innerBoundaryIs"):
                        continue
                    for co in b.iter():
                        if _local(co.tag) == "coordinates":
                            ring = _kml_coords(co.text)
                            (rings.insert(0, ring) if bt == "outerBoundaryIs" else rings.append(ring))
                polys.append(rings)
            elif t == "Point":
                for co in el.iter():
                    if _local(co.tag) == "coordinates":
                        c = _kml_coords(co.text)
                        if c:
                            points.append(c[0])
            elif t == "LineString":
                lines += 1
        if polys:
            geom = ({"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1
                    else {"type": "MultiPolygon", "coordinates": polys})
        elif points:
            geom = ({"type": "Point", "coordinates": points[0]} if len(points) == 1
                    else {"type": "MultiPoint", "coordinates": points})
        else:
            geom = {"type": "LineString" if lines else "Empty", "coordinates": []}
        raws.append(_raw_from_props({"name": name} if name else {}, geom, f"#{i}", i))
    if not raws:
        return [], [_issue("E_KML_EMPTY", "error", "KML không có Placemark nào.",
                           "The KML has no Placemark.")]
    return raws, []


def _csv_num(s: str, decimal_comma: bool):
    s = (s or "").strip()
    if not s:
        return None
    if decimal_comma:
        s = (s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1
             else s.replace(",", "."))
    try:
        return _D(s)
    except ValueError:
        return None


def _parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """CSV: mỗi dòng một thửa. Toạ độ điểm (lat, lon) HOẶC cột ranh dạng WKT
    (POLYGON((lon lat, …))) / GeoJSON. Excel tiếng Việt: ';' + dấu phẩy thập phân."""
    from app.services.batch import _COLS, _norm

    first = text.splitlines()[0] if text.splitlines() else ""
    delim = max((";", ",", "\t"), key=first.count)
    decimal_comma = delim != ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    header = [_norm(h) for h in next(reader, [])]
    cols = dict(_COLS)
    cols["wkt"] = ("wkt", "polygon", "geometry", "geojson", "ranh", "ranh_thua", "da_giac")
    cols["producer"] = ("producername", "producer", "chu_ho", "chủ_hộ", "ho_ten", "họ_tên", "farmer")
    idx = {}
    for key, names in cols.items():
        normed = {_norm(n) for n in names}
        for i, h in enumerate(header):
            if h in normed:
                idx[key] = i
                break
    if "wkt" not in idx and ("lat" not in idx or "lon" not in idx):
        return [], [_issue("E_CSV_COLS", "error",
                           "Thiếu cột toạ độ: cần cột lat + lon (hoặc vi_do + kinh_do), hoặc một cột "
                           "ranh dạng WKT/GeoJSON (wkt, polygon, ranh).",
                           "Missing coordinate columns: need lat + lon, or a boundary column in "
                           "WKT/GeoJSON (wkt, polygon).")]
    raws, errs = [], []
    for n, rec in enumerate(reader, start=2):
        if not any(c.strip() for c in rec):
            continue

        def get(k):
            return rec[idx[k]].strip() if k in idx and idx[k] < len(rec) else ""
        props = {"ref": get("ref") or f"#{n - 1}", "producer": get("producer") or None}
        area = _csv_num(get("area_ha"), decimal_comma)
        if area is not None:
            props["area_ha"] = float(area)
        w = get("wkt")
        geom = None
        if w:
            geom = _geom_from_text(w)
            if geom is None:
                errs.append(_issue("E_CSV_WKT", "error",
                                   f"Dòng {n}: cột ranh không đọc được (cần WKT POLYGON((kinh_độ vĩ_độ, …)) "
                                   "hoặc GeoJSON).",
                                   f"Line {n}: boundary column unreadable (need WKT POLYGON((lon lat, …)) "
                                   "or GeoJSON).", line=n))
                continue
        else:
            lat, lon = _csv_num(get("lat"), decimal_comma), _csv_num(get("lon"), decimal_comma)
            if lat is None or lon is None:
                errs.append(_issue("E_CSV_NUM", "error", f"Dòng {n}: toạ độ không phải số.",
                                   f"Line {n}: coordinates are not numbers.", line=n))
                continue
            geom = {"type": "Point", "coordinates": [lon, lat]}
        raws.append(_raw_from_props(props, geom, tr(f"dòng {n}", f"line {n}"), n - 1))
    return raws, errs


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _geom_from_text(s: str) -> dict | None:
    s = s.strip()
    if s.startswith("{"):
        try:
            g = json.loads(s, parse_float=_D, parse_int=_D)
            return g.get("geometry", g) if isinstance(g, dict) else None
        except json.JSONDecodeError:
            return None
    m = re.match(r"^\s*(MULTIPOLYGON|POLYGON|POINT)\s*(\(.*\))\s*$", s, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    kind, body = m.group(1).upper(), m.group(2)

    def ring(txt):
        pts = []
        for pair in txt.split(","):
            nums = _NUM.findall(pair)
            if len(nums) < 2:
                return None
            pts.append([_D(nums[0]), _D(nums[1])])
        return pts
    try:
        if kind == "POINT":
            nums = _NUM.findall(body)
            return {"type": "Point", "coordinates": [_D(nums[0]), _D(nums[1])]}
        if kind == "POLYGON":
            rings = [ring(r) for r in re.findall(r"\(([^()]*)\)", body)]
            return None if not rings or any(r is None for r in rings) else \
                {"type": "Polygon", "coordinates": rings}
        polys = []
        for p in re.findall(r"\(((?:\s*\([^()]*\)\s*,?)+)\)", body):
            rings = [ring(r) for r in re.findall(r"\(([^()]*)\)", p)]
            if not rings or any(r is None for r in rings):
                return None
            polys.append(rings)
        return {"type": "MultiPolygon", "coordinates": polys} if polys else None
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------ kiểm một thửa

def _in_vn(lat: float, lon: float) -> bool:
    return VN_LAT[0] <= lat <= VN_LAT[1] and VN_LON[0] <= lon <= VN_LON[1]


def _positions(typ: str, coords) -> list:
    """Danh sách MỌI vị trí [lon, lat] (tham chiếu, sửa tại chỗ được)."""
    if typ == "Point":
        return [coords]
    if typ == "MultiPoint":
        return list(coords)
    if typ == "Polygon":
        return [p for ring in coords for p in ring]
    return [p for poly in coords for ring in poly for p in ring]


def _check_position(p) -> bool:
    return (isinstance(p, (list, tuple)) and len(p) >= 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(float(v)) for v in p[:2]))


def _spikes(ring_m: list[tuple[float, float]]) -> int:
    pts = ring_m[:-1]
    n, bad = len(pts), 0
    if n < 4:
        return 0
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = (a[0] - b[0], a[1] - b[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < SPIKE_MIN_M or l2 < SPIKE_MIN_M:
            continue
        cosang = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        if math.degrees(math.acos(cosang)) < SPIKE_DEG:
            bad += 1
    return bad


def _round_ring(coords) -> list[list[float]]:
    out = []
    for x, y in coords:
        p = [round(float(x), EU_MIN_DECIMALS), round(float(y), EU_MIN_DECIMALS)]
        if not out or p != out[-1]:
            out.append(p)
    if out and out[0] != out[-1]:
        out.append(list(out[0]))
    return out


def _eu_polygon_coords(poly: Polygon) -> list:
    """Ranh ngoài, ngược chiều kim đồng hồ (RFC 7946), làm tròn 6 chữ số."""
    return [_round_ring(orient(poly, 1.0).exterior.coords)]


def validate_raw(raw: dict, index: int = 0) -> dict:
    """Kiểm MỘT thửa thô → thửa đã chuẩn hoá + danh sách vấn đề."""
    issues: list[dict] = []
    g = raw.get("geom")
    typ = g.get("type") if isinstance(g, dict) else None
    plot = {"index": index, "ref": raw.get("ref") or f"#{index + 1}", "src": raw.get("src"),
            "producer": raw.get("producer"), "country": raw.get("country"),
            "area_declared_ha": raw.get("area_declared"), "kind": None, "geometry": None,
            "area_ha": None, "area_source": None, "centroid": None, "bbox": None,
            "n_vertices": 0, "issues": issues, "valid": False}

    if typ not in EU_GEOM_TYPES:
        issues.append(_issue(
            "E_GEOM_TYPE", "error",
            f"Kiểu hình học “{typ or 'không có'}” không được EU nhận. Ranh thửa phải là vùng khép kín "
            "(Polygon/MultiPolygon) hoặc điểm (Point) — đường kẻ (LineString) bị từ chối.",
            f"Geometry type “{typ or 'none'}” is not accepted by the EU. A plot must be a closed area "
            "(Polygon/MultiPolygon) or a point — lines (LineString) are rejected."))
        return plot
    coords = g.get("coordinates")
    try:
        pos = _positions(typ, coords)
    except (TypeError, IndexError):
        pos = None
    if not pos or not all(_check_position(p) for p in pos):
        issues.append(_issue("E_COORDS", "error", "Toạ độ hỏng hoặc thiếu (cần [kinh độ, vĩ độ] là số).",
                             "Coordinates broken or missing (need numeric [longitude, latitude])."))
        return plot

    # Kinh/vĩ độ bị đảo: lỗi rất hay gặp khi dán từ Excel (cột vĩ độ đứng trước).
    lats, lons = [float(p[1]) for p in pos], [float(p[0]) for p in pos]
    in_vn = all(_in_vn(la, lo) for la, lo in zip(lats, lons))
    if not in_vn and all(_in_vn(lo, la) for la, lo in zip(lats, lons)):
        for p in pos:
            p[0], p[1] = p[1], p[0]
        issues.append(_issue("F_SWAPPED", "fixed",
                             "Kinh độ và vĩ độ bị đảo chỗ — đã đổi lại (GeoJSON viết kinh độ TRƯỚC).",
                             "Longitude and latitude were swapped — fixed (GeoJSON puts longitude FIRST)."))
    elif any(not (-180 <= lo <= 180 and -90 <= la <= 90) for la, lo in zip(lats, lons)):
        issues.append(_issue("E_RANGE", "error", "Toạ độ nằm ngoài phạm vi kinh độ ±180 / vĩ độ ±90.",
                             "Coordinates outside longitude ±180 / latitude ±90."))
        return plot
    elif not in_vn:
        issues.append(_issue("W_OUTSIDE_VN", "warning", "Thửa nằm ngoài lãnh thổ Việt Nam — kiểm tra lại toạ độ.",
                             "The plot lies outside Vietnam — check the coordinates."))

    decs = [d for d in (_dec(v) for p in pos for v in p[:2]) if d is not None]
    if decs and max(decs) <= LOW_PRECISION_DECIMALS:
        e = _ERR_BY_DECIMALS.get(max(decs), "")
        issues.append(_issue(
            "W_PRECISION", "warning",
            f"Toạ độ chỉ có tối đa {max(decs)} chữ số thập phân (sai số tới ~{e}). Quy định EUDR yêu cầu "
            "ít nhất 6 chữ số — đo lại bằng GPS điện thoại.",
            f"Coordinates have at most {max(decs)} decimals (error up to ~{e}). The EUDR requires at least "
            "6 decimals — re-measure with phone GPS."))

    acc = raw.get("gps_accuracy_m")
    if acc is not None and acc > GPS_ACCURACY_WARN_M:
        issues.append(_issue(
            "W_GPS_ACCURACY", "warning",
            f"Độ chính xác GPS trung bình ~{acc:.0f} m lúc đo — ranh có thể lệch. Đo lại khi trời quang, "
            "đứng ra khỏi tán cây, chờ GPS ổn định.",
            f"Average GPS accuracy ~{acc:.0f} m while measuring — the boundary may be off. Re-measure under "
            "open sky, away from tree canopy."))

    if typ in ("Point", "MultiPoint"):
        _finish_point(plot, typ, pos, raw, issues)
    else:
        _finish_polygon(plot, typ, coords, raw, issues)
    plot["valid"] = not any(i["level"] == "error" for i in issues)
    return plot


def _finish_point(plot: dict, typ: str, pos: list, raw: dict, issues: list) -> None:
    pts = [[round(float(p[0]), EU_MIN_DECIMALS), round(float(p[1]), EU_MIN_DECIMALS)] for p in pos]
    plot["kind"] = "point"
    plot["geometry"] = ({"type": "Point", "coordinates": pts[0]} if typ == "Point"
                        else {"type": "MultiPoint", "coordinates": pts})
    plot["n_vertices"] = len(pts)
    lon_c = sum(p[0] for p in pts) / len(pts)
    lat_c = sum(p[1] for p in pts) / len(pts)
    plot["centroid"] = {"lat": round(lat_c, 6), "lon": round(lon_c, 6)}
    plot["bbox"] = [min(p[0] for p in pts), min(p[1] for p in pts),
                    max(p[0] for p in pts), max(p[1] for p in pts)]
    a = raw.get("area_declared")
    if a is not None and a > EU_POINT_MAX_HA:
        issues.append(_issue(
            "E_POINT_OVER_4HA", "error",
            f"Thửa {a:g} ha mà chỉ khai một điểm. EUDR Điều 9(1)(d): thửa trên 4 ha phải khai bằng ĐA GIÁC "
            "(ranh thửa) — đi bộ quanh vườn hoặc vẽ ranh.",
            f"A {a:g} ha plot declared as a single point. EUDR Art. 9(1)(d): plots over 4 ha must be "
            "declared as a POLYGON — walk or draw the boundary."))
    if a is None or a <= 0:
        issues.append(_issue(
            "W_POINT_NO_AREA", "warning",
            "Điểm không khai diện tích — hệ thống EU sẽ mặc định 4 ha. Nên khai diện tích thật (cột area_ha), "
            "hoặc tốt hơn: đo ranh thửa.",
            "Point without an area — the EU system will assume 4 ha. Declare the real area (area_ha), or "
            "better: measure the boundary."))
        plot["area_ha"], plot["area_source"] = EU_DEFAULT_POINT_HA, "eu_default"
    else:
        plot["area_ha"], plot["area_source"] = round(a, 4), "declared"


def _finish_polygon(plot: dict, typ: str, coords, raw: dict, issues: list) -> None:
    polys_in = [coords] if typ == "Polygon" else list(coords)
    lon0 = sum(float(p[0]) for p in _positions(typ, coords)) / max(1, len(_positions(typ, coords)))
    parts: list[Polygon] = []
    for k, rings in enumerate(polys_in):
        label = tr(f" (phần {k + 1})", f" (part {k + 1})") if len(polys_in) > 1 else ""
        if not rings or not rings[0]:
            issues.append(_issue("E_EMPTY_RING", "error", f"Ranh rỗng{label}.", f"Empty ring{label}."))
            continue
        ext = [(float(p[0]), float(p[1])) for p in rings[0]]
        ded = [ext[0]] + [p for i, p in enumerate(ext[1:], 1) if p != ext[i - 1]]
        if len(ded) < len(ext):
            issues.append(_issue("F_DUP_POINTS", "fixed",
                                 f"Bỏ {len(ext) - len(ded)} điểm trùng liền nhau{label}.",
                                 f"Removed {len(ext) - len(ded)} consecutive duplicate point(s){label}."))
        if ded[0] != ded[-1]:
            ded.append(ded[0])
            issues.append(_issue("F_CLOSED", "fixed",
                                 f"Ranh chưa khép kín — đã nối điểm cuối về điểm đầu{label}.",
                                 f"Ring was open — closed it back to the first point{label}."))
        if len(set(ded[:-1])) < 3:
            issues.append(_issue("E_TOO_FEW", "error", f"Ranh cần ít nhất 3 điểm khác nhau{label}.",
                                 f"A boundary needs at least 3 distinct points{label}."))
            continue
        if len(rings) > 1:
            issues.append(_issue(
                "E_HOLES", "error",
                f"Ranh có {len(rings) - 1} lỗ thủng bên trong{label} — EU không nhận đa giác có lỗ. Tách phần "
                "đất sản xuất thành nhiều đa giác KHÔNG có lỗ (MultiPolygon).",
                f"The boundary has {len(rings) - 1} hole(s){label} — the EU does not accept polygons with "
                "holes. Split the production area into several hole-free polygons (MultiPolygon)."))
        poly = Polygon(ded)
        if not poly.is_valid:
            why = explain_validity(poly)
            m = re.search(r"\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\]", why)
            where = (tr(f" gần toạ độ {float(m.group(2)):.6f}, {float(m.group(1)):.6f}",
                        f" near {float(m.group(2)):.6f}, {float(m.group(1)):.6f}") if m else "")
            if "Self-intersection" in why or "Ring Self-intersection" in why:
                issues.append(_issue(
                    "E_SELF_INTERSECT", "error",
                    f"Đường ranh tự cắt nhau (hình số 8){where}{label} — EU từ chối. Đi hoặc vẽ lại theo MỘT "
                    "vòng, các điểm nối theo thứ tự quanh mép thửa.",
                    f"The boundary crosses itself (figure eight){where}{label} — rejected by the EU. Walk or "
                    "draw it again as ONE loop, points in order around the edge."))
            else:
                issues.append(_issue("E_INVALID", "error", f"Ranh không hợp lệ{label}: {why}.",
                                     f"Invalid boundary{label}: {why}."))
            continue
        nsp = _spikes(list(to_metric(poly, lon0).exterior.coords))
        if nsp:
            issues.append(_issue(
                "W_SPIKE", "warning",
                f"Ranh có {nsp} mũi nhọn bất thường{label} — dấu hiệu GPS nhảy điểm. Xem lại trên bản đồ.",
                f"The boundary has {nsp} abnormal spike(s){label} — a sign of GPS jumps. Review it on the map."))
        parts.append(poly)

    if not parts:
        return
    geom = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    if len(parts) > 1 and not geom.is_valid:
        issues.append(_issue("E_PARTS_OVERLAP", "error",
                             "Các phần của thửa chồng lên nhau — mỗi phần phải tách rời.",
                             "Parts of this plot overlap each other — each part must be separate."))
    if any(i["level"] == "error" for i in issues):
        return
    plot["kind"] = "polygon"
    eu_parts = [_eu_polygon_coords(p) for p in parts]
    plot["geometry"] = ({"type": "Polygon", "coordinates": eu_parts[0]} if len(eu_parts) == 1
                        else {"type": "MultiPolygon", "coordinates": eu_parts})
    plot["n_vertices"] = sum(len(p[0]) - 1 for p in eu_parts)
    a = area_ha(geom, lon0)
    plot["area_ha"], plot["area_source"] = round(a, 4), "polygon"
    c = geom.centroid
    plot["centroid"] = {"lat": round(c.y, 6), "lon": round(c.x, 6)}
    plot["bbox"] = [round(v, 6) for v in geom.bounds]
    if a < TINY_HA:
        issues.append(_issue("W_TINY", "warning",
                             f"Thửa chỉ ~{a * 10000:.0f} m² — thường là GPS nhảy hoặc nhầm đơn vị. Kiểm tra lại.",
                             f"The plot is only ~{a * 10000:.0f} m² — usually a GPS jump or unit mix-up. Check it."))
    elif a > HUGE_HA:
        issues.append(_issue("W_HUGE", "warning", f"Thửa rộng {a:,.0f} ha — kiểm tra có đúng một thửa.",
                             f"The plot covers {a:,.0f} ha — check it is really one plot."))
    d = raw.get("area_declared")
    if d and d > 0 and abs(a - d) / d * 100 > AREA_MISMATCH_PCT:
        issues.append(_issue(
            "W_AREA_MISMATCH", "warning",
            f"Diện tích khai {d:g} ha nhưng ranh đo được {a:.2f} ha (lệch {abs(a - d) / d * 100:.0f}%). "
            "Kiểm tra ranh hoặc số khai.",
            f"Declared area {d:g} ha but the boundary measures {a:.2f} ha ({abs(a - d) / d * 100:.0f}% off). "
            "Check the boundary or the declared figure."))


# ------------------------------------------------------------------ kiểm chéo các thửa

def _shape(plot: dict, lon0: float):
    g = plot["geometry"]
    if plot["kind"] == "polygon":
        if g["type"] == "Polygon":
            geom = Polygon(g["coordinates"][0])
        else:
            geom = MultiPolygon([Polygon(p[0]) for p in g["coordinates"]])
        return to_metric(geom, lon0)
    c = plot["centroid"]
    return to_metric(Point(c["lon"], c["lat"]), lon0)


def cross_check(plots: list[dict]) -> None:
    """Hai hộ khai CHỒNG lên nhau / trùng hệt nhau / điểm nằm trong ranh thửa khác.
    Ghi thẳng vào issues của từng thửa (cả hai phía)."""
    usable = [p for p in plots if p.get("geometry") and p.get("centroid")]
    if len(usable) < 2:
        return
    lon0 = sum(p["centroid"]["lon"] for p in usable) / len(usable)
    shapes = [_shape(p, lon0) for p in usable]
    tree = STRtree(shapes)
    seen: set[tuple[int, int]] = set()
    for i, (p, s) in enumerate(zip(usable, shapes)):
        probe = s.buffer(POINT_DUP_M) if s.geom_type == "Point" else s
        for j in tree.query(probe):
            j = int(j)
            if j == i or (min(i, j), max(i, j)) in seen:
                continue
            seen.add((min(i, j), max(i, j)))
            q, t = usable[j], shapes[j]
            _pair(p, s, q, t)
    for p in plots:
        if any(x["level"] == "error" for x in p["issues"]):
            p["valid"] = False


def _pair(p: dict, s, q: dict, t) -> None:
    def both(code, level, vi_fn, en_fn):
        p["issues"].append(_issue(code, level, vi_fn(q["ref"]), en_fn(q["ref"]), other=q["ref"]))
        q["issues"].append(_issue(code, level, vi_fn(p["ref"]), en_fn(p["ref"]), other=p["ref"]))

    if s.geom_type == "Point" and t.geom_type == "Point":
        d = s.distance(t)
        if d <= POINT_DUP_M:
            both("W_POINT_DUP", "warning",
                 lambda o: f"Cách điểm của thửa {o} chỉ {d:.1f} m — có thể khai trùng một thửa hai lần.",
                 lambda o: f"Only {d:.1f} m from plot {o}'s point — possibly the same plot declared twice.")
        return
    if s.geom_type == "Point" or t.geom_type == "Point":
        pt, poly, pp, qq = (s, t, p, q) if s.geom_type == "Point" else (t, s, q, p)
        if poly.contains(pt):
            pp["issues"].append(_issue(
                "W_POINT_IN_PLOT", "warning",
                f"Điểm này nằm TRONG ranh thửa {qq['ref']} — có thể khai trùng.",
                f"This point lies INSIDE plot {qq['ref']}'s boundary — possibly a duplicate.", other=qq["ref"]))
        return
    inter = s.intersection(t).area
    if inter <= 0:
        return
    small = min(s.area, t.area)
    pct = 100.0 * inter / small if small > 0 else 0.0
    if s.symmetric_difference(t).area <= 0.001 * max(s.area, t.area):
        both("E_DUPLICATE", "error",
             lambda o: f"Ranh trùng hệt thửa {o} — một thửa khai hai lần.",
             lambda o: f"Boundary identical to plot {o} — one plot declared twice.")
    elif pct >= OVERLAP_ERROR_PCT:
        both("E_OVERLAP", "error",
             lambda o: f"Chồng lên thửa {o} khoảng {inter / 10000:.2f} ha ({pct:.0f}% thửa nhỏ hơn) — hai hộ "
                       "không thể cùng khai một mảnh đất. Đo lại ranh chung.",
             lambda o: f"Overlaps plot {o} by about {inter / 10000:.2f} ha ({pct:.0f}% of the smaller plot) — two "
                       "producers cannot declare the same land. Re-measure the shared edge.")
    elif pct >= OVERLAP_WARN_PCT:
        both("W_OVERLAP_EDGE", "warning",
             lambda o: f"Mép ranh chồng nhẹ lên thửa {o} ({pct:.1f}%) — thường do sai số GPS; nên chỉnh.",
             lambda o: f"Edge slightly overlaps plot {o} ({pct:.1f}%) — usually GPS error; worth fixing.")


# ------------------------------------------------------------------ toàn bộ tệp

def validate_text(text: str, filename: str = "") -> dict:
    raws, file_errors, fmt = parse(text, filename)
    plots = [validate_raw(r, i) for i, r in enumerate(raws)]
    cross_check(plots)
    return {"format": fmt, "file_errors": file_errors, "plots": plots, "summary": summarize(plots, file_errors)}


def validate_geometry(geometry: dict, ref: str = "", area_declared: float | None = None,
                      gps_accuracy_m: float | None = None, producer: str | None = None) -> dict:
    """Một thửa vẽ/đi bộ trên app (không có số chữ số gốc → bỏ qua kiểm chữ số)."""
    raw = {"ref": ref or tr("Vườn của tôi", "My plot"), "producer": producer, "country": "VN",
           "area_declared": area_declared, "gps_accuracy_m": gps_accuracy_m,
           "geom": json.loads(json.dumps(geometry)), "src": "app"}
    return validate_raw(raw, 0)


def summarize(plots: list[dict], file_errors: list[dict] | None = None) -> dict:
    by_code: dict[str, int] = {}
    for p in plots:
        for i in p["issues"]:
            by_code[i["code"]] = by_code.get(i["code"], 0) + 1
    n_valid = sum(1 for p in plots if p["valid"])
    n_err = len(plots) - n_valid
    n_warn = sum(1 for p in plots if p["valid"] and any(i["level"] == "warning" for i in p["issues"]))
    n_fixed = sum(1 for p in plots if any(i["level"] == "fixed" for i in p["issues"]))
    total = sum(p["area_ha"] or 0 for p in plots if p["valid"])
    ready = bool(plots) and n_err == 0 and not any(e["level"] == "error" for e in (file_errors or []))
    return {
        "n": len(plots), "n_valid": n_valid, "n_errors": n_err, "n_warnings": n_warn, "n_fixed": n_fixed,
        "n_polygons": sum(1 for p in plots if p["kind"] == "polygon"),
        "n_points": sum(1 for p in plots if p["kind"] == "point"),
        "total_ha": round(total, 2), "by_code": by_code, "eu_ready": ready,
        "headline": (tr(f"Cả {len(plots)} thửa đạt chuẩn tệp GeoJSON của EU"
                        + (f" ({n_fixed} thửa đã tự sửa lỗi nhỏ)" if n_fixed else "") + ".",
                        f"All {len(plots)} plots meet the EU GeoJSON rules"
                        + (f" ({n_fixed} had minor issues auto-fixed)" if n_fixed else "") + ".")
                     if ready else
                     tr(f"{n_err}/{len(plots)} thửa có lỗi EU sẽ từ chối — sửa trước khi nộp.",
                        f"{n_err}/{len(plots)} plots have errors the EU will reject — fix them before filing.")
                     if plots else tr("Không đọc được thửa nào.", "No plot could be read.")),
    }


def to_eu_geojson(plots: list[dict], producer_name: str | None = None, country: str = "VN",
                  only_valid: bool = True) -> dict:
    """FeatureCollection đúng mẫu TRACES. Thuộc tính rỗng bỏ hẳn (không ghi null)."""
    feats = []
    for p in plots:
        if (only_valid and not p["valid"]) or not p.get("geometry"):
            continue
        props = {"ProducerName": p.get("producer") or producer_name,
                 "ProducerCountry": (p.get("country") or country or "VN").upper()[:2],
                 "ProductionPlace": p.get("ref")}
        if p["kind"] == "point" and p.get("area_source") == "declared":
            props["Area"] = p["area_ha"]
        feats.append({"type": "Feature", "properties": {k: v for k, v in props.items() if v not in (None, "")},
                      "geometry": p["geometry"]})
    return {"type": "FeatureCollection", "features": feats}


def shapely_geom(plot: dict):
    """Hình học lon/lat (shapely) của thửa đã chuẩn hoá. Điểm → hình tròn đúng diện
    tích khai (hoặc 4 ha mặc định của EU) — ghi rõ ở nơi dùng."""
    g = plot["geometry"]
    if plot["kind"] == "polygon":
        if g["type"] == "Polygon":
            return Polygon(g["coordinates"][0])
        return MultiPolygon([Polygon(p[0]) for p in g["coordinates"]])
    c = plot["centroid"]
    lon0 = c["lon"]
    r = math.sqrt((plot.get("area_ha") or EU_DEFAULT_POINT_HA) * 10_000.0 / math.pi)
    pts = [Point(x, y) for x, y in (g["coordinates"] if g["type"] == "MultiPoint" else [g["coordinates"]])]
    circles = [from_metric(to_metric(pt, lon0).buffer(r, 32), lon0) for pt in pts]
    return circles[0] if len(circles) == 1 else unary_union(circles)


def geojson_of(geom) -> dict:
    return json.loads(json.dumps(mapping(geom)))
