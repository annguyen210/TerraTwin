"""TerraTwin SDK — thư viện Python một file cho Twin API.

Cài: chỉ cần copy file này vào dự án. Không phụ thuộc gói ngoài (chỉ dùng thư
viện chuẩn), nên chạy được ở mọi nơi có Python 3.9+.

    from terratwin import TerraTwin

    tt = TerraTwin(api_key="tt_...")          # tạo khóa ở tab Tài khoản
    scan = tt.scan(10.19, 106.70)
    print(scan["terrascore"]["score"], scan["terrascore"]["grade"])

    for a in scan["alerts"]:
        print(a["name"], "→", a["headline"])

Xác thực: dùng khóa API (`X-API-Key`) hoặc token đăng nhập (`Bearer`).
Các endpoint công khai (assess/scan/backtest…) không cần khóa.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.0.0"

DEFAULT_BASE_URL = "http://localhost:8000"


class TerraTwinError(RuntimeError):
    """Lỗi từ API. `status` là mã HTTP, `detail` là thông báo của máy chủ."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class TerraTwin:
    """Client cho TerraTwin API."""

    def __init__(self, api_key: str | None = None, token: str | None = None,
                 base_url: str = DEFAULT_BASE_URL, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.token = token
        self.timeout = timeout

    # ---------- lõi ----------

    def _headers(self) -> dict:
        h = {"content-type": "application/json",
             "user-agent": f"terratwin-python/{__version__}"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        elif self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, method: str, path: str, body=None, params=None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None})
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(),
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.reason
            try:
                d = json.loads(e.read().decode("utf-8"))
                got = d.get("detail", detail)
                # Lỗi validate của FastAPI là list — lấy thông báo đầu tiên.
                detail = got[0].get("msg", str(got)) if isinstance(got, list) and got else got
            except Exception:
                pass
            raise TerraTwinError(e.code, str(detail)) from None
        except urllib.error.URLError as e:
            raise TerraTwinError(0, f"Không kết nối được {self.base_url}: {e.reason}") from None

    @staticmethod
    def _loc(lat: float, lon: float, area_ha: float | None = None) -> dict:
        d = {"lat": lat, "lon": lon}
        if area_ha is not None:
            d["area_ha"] = area_ha
        return d

    # ---------- công khai (không cần khóa) ----------

    def health(self) -> dict:
        return self._request("GET", "/api/health")

    def modules(self) -> list:
        """14 mũi nhọn và trạng thái dữ liệu của từng cái."""
        return self._request("GET", "/api/modules")

    def assess(self, module_id: str, lat: float, lon: float,
               area_ha: float | None = None) -> dict:
        return self._request("POST", f"/api/assess/{module_id}",
                             self._loc(lat, lon, area_ha))

    def scan(self, lat: float, lon: float, area_ha: float | None = None) -> dict:
        """Quét cả 14 module + TerraScore + cảnh báo ưu tiên trong một lần."""
        return self._request("POST", "/api/scan", self._loc(lat, lon, area_ha))

    def terrascore(self, lat: float, lon: float) -> dict:
        return self._request("POST", "/api/terrascore", self._loc(lat, lon))

    def whatif(self, module_id: str, lat: float, lon: float) -> dict:
        """C02 — bốn kịch bản thời tiết song song."""
        return self._request("POST", f"/api/whatif/{module_id}", self._loc(lat, lon))

    def explain(self, module_id: str, lat: float, lon: float) -> dict:
        """S07 — vì sao chỉ số cao, phân rã đóng góp từng yếu tố."""
        return self._request("POST", f"/api/explain/{module_id}", self._loc(lat, lon))

    def goalseek(self, module_id: str, lat: float, lon: float,
                 target: float | None = None) -> dict:
        """S03 — cần điều kiện gì để an toàn."""
        return self._request("POST", f"/api/goalseek/{module_id}",
                             self._loc(lat, lon), {"target": target})

    def timemachine(self, module_id: str, lat: float, lon: float,
                    years: int = 10) -> dict:
        """S02 — xác suất vượt ngưỡng suy từ N năm thật."""
        return self._request("POST", f"/api/timemachine/{module_id}",
                             self._loc(lat, lon), {"years": years})

    def anomaly(self, lat: float, lon: float, years: int = 10) -> dict:
        """C10 — tuần này có bất thường so với khí hậu nền không."""
        return self._request("POST", "/api/anomaly", self._loc(lat, lon),
                             {"years": years})

    def heatmap(self, module_id: str, lat: float, lon: float,
                side: int = 7, radius_km: float = 8.0) -> dict:
        """C06 — lưới rủi ro quanh thửa."""
        return self._request("POST", f"/api/heatmap/{module_id}",
                             self._loc(lat, lon),
                             {"side": side, "radius_km": radius_km})

    def genome(self, lat: float, lon: float, k: int = 5) -> dict:
        """S04 — tìm vùng có bộ gen đất đai giống thửa của bạn."""
        return self._request("POST", "/api/genome", self._loc(lat, lon), {"k": k})

    def ask(self, question: str, lat: float, lon: float,
            module_id: str = "flood") -> dict:
        """C03 — hỏi What-If bằng lời."""
        return self._request("POST", "/api/ask", {
            "question": question, "location": self._loc(lat, lon),
            "module_id": module_id})

    def build_twin(self, lat: float, lon: float,
                   area_ha: float | None = None) -> dict:
        """C01 — dựng bản sao số đầy đủ (không lưu)."""
        return self._request("POST", "/api/twin", self._loc(lat, lon, area_ha))

    def backtests(self) -> list:
        return self._request("GET", "/api/backtest")

    def backtest(self, event_id: str) -> dict:
        """Kiểm chứng 'biết trước' trên một thiên tai lịch sử có thật."""
        return self._request("GET", f"/api/backtest/{event_id}")

    # ---------- cần khóa ----------

    def me(self) -> dict:
        return self._request("GET", "/api/auth/me")

    def plots(self) -> list:
        return self._request("GET", "/api/plots")

    def save_plot(self, name: str, lat: float, lon: float,
                  area_ha: float | None = None, score: int | None = None,
                  grade: str | None = None) -> dict:
        return self._request("POST", "/api/plots", {
            "name": name, "location": self._loc(lat, lon, area_ha),
            "score": score, "grade": grade})

    def delete_plot(self, plot_id: int) -> None:
        self._request("DELETE", f"/api/plots/{plot_id}")

    def twins(self) -> list:
        return self._request("GET", "/api/twins")

    def save_twin(self, name: str, lat: float, lon: float,
                  area_ha: float | None = None) -> dict:
        """C01 — dựng rồi LƯU Twin (ảnh chụp tại thời điểm dựng)."""
        return self._request("POST", "/api/twins", {
            "name": name, "location": self._loc(lat, lon, area_ha)})

    def twin(self, twin_id: int) -> dict:
        return self._request("GET", f"/api/twins/{twin_id}")

    def run_radar(self) -> dict:
        """C05 — quét lại mọi thửa đã lưu và gửi cảnh báo mới."""
        return self._request("POST", "/api/radar/run")

    def alerts(self, unread_only: bool = False, limit: int = 50) -> list:
        return self._request("GET", "/api/alerts",
                             params={"unread_only": str(unread_only).lower(),
                                     "limit": limit})

    def channels(self) -> list:
        """U01 — các kênh nhận cảnh báo."""
        return self._request("GET", "/api/channels")

    def add_channel(self, kind: str, target: str,
                    min_level: str = "warning") -> dict:
        return self._request("POST", "/api/channels", {
            "kind": kind, "target": target, "min_level": min_level})

    def test_channel(self, channel_id: int) -> dict:
        return self._request("POST", f"/api/channels/{channel_id}/test")

    def upload_csv(self, name: str, content: str) -> dict:
        """C11 — tải danh sách thửa lên để chấm hàng loạt."""
        return self._request("POST", "/api/datasets", {
            "name": name, "kind": "csv", "content": content})

    def score_dataset(self, dataset_id: int, limit: int = 50) -> dict:
        return self._request("POST", f"/api/datasets/{dataset_id}/score",
                             params={"limit": limit})


if __name__ == "__main__":       # ví dụ chạy nhanh
    import sys
    tt = TerraTwin(base_url=sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL)
    print("health:", tt.health())
    s = tt.scan(10.19, 106.70)
    ts = s["terrascore"]
    print(f"TerraScore {ts['score']}/100 hạng {ts['grade']}")
    for a in s["alerts"]:
        print(f"  ⚠️  {a['name']}: {a['headline']}")
