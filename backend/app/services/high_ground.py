"""CHỖ CAO GẦN NHẤT — khi nước lên, đi hướng nào để tới chỗ cao hơn mà ít phải lội qua vùng trũng (nâng cấp 25/11/2026).

Lưới độ cao 25 × 25 ô, cách nhau 125 m quanh thửa (±1,5 km, DEM ~30 m qua Open-Meteo, 625 điểm trong 7 lượt gọi). Thuật
toán Dijkstra trên đồ thị 8 hướng: chi phí một bước = quãng đường × (1 + 3 nếu ô đến THẤP HƠN thửa) — vùng trũng hơn thửa
ngập trước, nên đường đi tránh nó khi có thể. Đích = ô gần nhất (theo chi phí) cao hơn thửa ≥ `rise` mét.

GIỚI HẠN — NÓI RA: không có đường sá, cầu, kênh, nhà cửa; DEM sai số vài mét ở đồng bằng; không phải chỉ dẫn sơ tán chính
thức. Dùng để biết TRƯỚC hướng có đất cao gần nhà — khi có lệnh sơ tán, làm theo chính quyền địa phương.
"""
from __future__ import annotations

import heapq
import math

from app.services import cache_store
from app.services.reqlang import tr

N = 25                  # ô mỗi cạnh
STEP_M = 125.0
LOW_PENALTY = 3.0
_TTL = 90 * 86400       # địa hình không đổi
_DIRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_HUONG = ["Bắc", "Đông Bắc", "Đông", "Đông Nam", "Nam", "Tây Nam", "Tây", "Tây Bắc"]
_DIR_EN = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def grid(lat: float, lon: float) -> list[tuple[float, float]]:
    """Toạ độ tâm các ô, hàng 0 ở phía BẮC; ô giữa (N//2, N//2) là thửa."""
    dlat = STEP_M / 111_320.0
    dlon = STEP_M / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    h = N // 2
    return [(lat + (h - r) * dlat, lon + (c - h) * dlon) for r in range(N) for c in range(N)]


def route(elev: list[float | None], rise: float) -> dict | None:
    """Dijkstra trên lưới (thuần, không mạng). → {path: [(r,c)…], dist_m, cost_m, target_elev, low_steps} hoặc None."""
    h = N // 2
    e0 = elev[h * N + h]
    if e0 is None:
        return None
    goal = e0 + rise
    best = {(h, h): 0.0}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    pq = [(0.0, h, h)]
    while pq:
        cost, r, c = heapq.heappop(pq)
        if cost > best.get((r, c), math.inf):
            continue
        e = elev[r * N + c]
        if (r, c) != (h, h) and e is not None and e >= goal:
            path = [(r, c)]
            while path[-1] in prev:
                path.append(prev[path[-1]])
            path.reverse()
            dist = sum(STEP_M * math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(path, path[1:]))
            low = sum(1 for (pr, pc) in path[1:] if (elev[pr * N + pc] or e0) < e0)
            return {"path": path, "dist_m": round(dist), "cost_m": round(cost), "target_elev": e, "plot_elev": e0,
                    "low_steps": low}
        for dr, dc in _DIRS:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < N and 0 <= cc < N):
                continue
            en = elev[rr * N + cc]
            if en is None:
                continue
            step = STEP_M * math.hypot(dr, dc) * (1 + (LOW_PENALTY if en < e0 else 0.0))
            nc = cost + step
            if nc < best.get((rr, cc), math.inf):
                best[(rr, cc)] = nc
                prev[(rr, cc)] = (r, c)
                heapq.heappush(pq, (nc, rr, cc))
    return None


def _bearing_idx(r: int, c: int) -> int:
    h = N // 2
    ang = (math.degrees(math.atan2(c - h, h - r)) + 360) % 360      # 0 = Bắc, theo chiều kim đồng hồ
    return int((ang + 22.5) // 45) % 8


def find(lat: float, lon: float, rise: float = 3.0) -> dict:
    rise = max(1.0, min(15.0, float(rise)))
    key = cache_store.make_key("high-ground", 1, round(lat, 4), round(lon, 4), rise)
    hit = cache_store.get(key)
    if hit is not None:
        return _texts(hit)
    from app.services import realdata
    pts = grid(lat, lon)
    elev = realdata.elevation_multi(pts)
    if sum(v is not None for v in elev) < 0.8 * len(elev):
        return {"available": False, "message": tr("Chưa lấy được độ cao quanh thửa (dịch vụ độ cao không phản hồi) — thử lại sau.",
                                                  "Could not read elevations around the plot (elevation service did not respond) — try later.")}
    r = route(elev, rise)
    if r is None:
        out = {"available": True, "found": False, "rise_m": rise, "radius_m": round(STEP_M * (N // 2)),
               "plot_elev": elev[(N // 2) * N + N // 2]}
    else:
        tr_, tc = r["path"][-1]
        out = {"available": True, "found": True, "rise_m": rise, "radius_m": round(STEP_M * (N // 2)),
               "plot_elev": r["plot_elev"], "target_elev": r["target_elev"], "dist_m": r["dist_m"], "low_steps": r["low_steps"],
               "target": {"lat": round(pts[tr_ * N + tc][0], 5), "lon": round(pts[tr_ * N + tc][1], 5)},
               "path": [[round(pts[a * N + b][1], 5), round(pts[a * N + b][0], 5)] for a, b in r["path"]],
               "dir_idx": _bearing_idx(tr_, tc)}
    cache_store.put(key, out, ttl_seconds=_TTL)
    return _texts(out)


def _texts(o: dict) -> dict:
    if not o.get("available"):
        return o
    caveat = tr("Tính từ mô hình độ cao ~30 m (sai số vài mét ở đồng bằng), KHÔNG biết đường sá, cầu, kênh — chỉ để biết trước "
                "hướng có đất cao; khi có lệnh sơ tán hãy làm theo chính quyền địa phương.",
                "From a ~30 m elevation model (a few metres of error on plains), WITHOUT roads, bridges or canals — only to know "
                "in advance where higher ground lies; when evacuation is ordered, follow local authorities.")
    if not o.get("found"):
        return {**o, "text": tr(f"Trong bán kính {o['radius_m']} m không có chỗ nào cao hơn thửa ≥ {o['rise_m']:g} m theo mô hình độ cao.",
                                f"No place within {o['radius_m']} m is ≥ {o['rise_m']:g} m higher than the plot per the elevation model."),
                "caveat": caveat}
    i = o["dir_idx"]
    low = (tr(f", đi qua {o['low_steps']} đoạn thấp hơn thửa", f", crossing {o['low_steps']} segment(s) lower than the plot")
           if o["low_steps"] else tr(", không phải đi qua chỗ thấp hơn thửa", ", without crossing ground lower than the plot"))
    return {**o, "caveat": caveat,
            "text": tr(f"Chỗ cao gần nhất (cao hơn thửa ≥ {o['rise_m']:g} m): khoảng {o['dist_m']} m về hướng {_HUONG[i]} — cao "
                       f"~{o['target_elev']:g} m so với ~{o['plot_elev']:g} m của thửa{low}.",
                       f"Nearest higher ground (≥ {o['rise_m']:g} m above the plot): about {o['dist_m']} m to the {_DIR_EN[i]} — "
                       f"~{o['target_elev']:g} m vs the plot's ~{o['plot_elev']:g} m{low}.")}
