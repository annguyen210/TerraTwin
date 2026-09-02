"use client";

/**
 * Màn hình đầu — hỏi "ruộng của bạn ở đâu" bằng tiếng người.
 *
 * VÌ SAO VIẾT LẠI. Trước đây mở app lên là một bản đồ trống, một dãy nút tên
 * "Nhóm A · Quang học", "Nhóm B · Radar & địa hình", và dòng hướng dẫn bảo bấm
 * một nút "Phân tích" KHÔNG TỒN TẠI. Người dùng phải đoán đúng ba bước mới thấy
 * được thứ gì, và nếu chọn nhầm mô-đun thì kết quả vô nghĩa. Phần mềm bắt người
 * ta học cấu trúc bên trong của nó trước khi cho họ bất kỳ giá trị nào.
 *
 * BA ĐƯỜNG VÀO, XẾP THEO ĐÚNG THỰC TẾ NGƯỜI DÙNG:
 *
 * ① ĐỊNH VỊ đứng đầu, không phải ô tìm kiếm. Người cần phần mềm này thường
 *    đang ĐỨNG NGAY TRÊN thửa đất của mình. Một chạm là xong, không phải gõ,
 *    không phải biết tên hành chính xã mình — thứ mà nhiều người thật sự không
 *    nhớ chính xác, nhất là sau các đợt sáp nhập đơn vị hành chính.
 *
 * ② GÕ TÊN là phụ, và có thể HỎNG. Nominatim là dịch vụ cộng đồng miễn phí và
 *    thực tế đã bị chặn khi thử từ máy phát triển. Vì vậy nó không bao giờ được
 *    làm đường vào duy nhất, và khi hỏng thì nói thẳng là đang hỏng rồi chỉ sang
 *    cách khác — chứ không để ô tìm kiếm im lặng không ra kết quả.
 *
 * ③ BẤM THẲNG BẢN ĐỒ luôn chạy được, không phụ thuộc gì cả.
 *
 * Danh sách chọn nhanh lấy đúng 16 toạ độ đã dùng để huấn luyện mô hình — đã
 * kiểm chứng là tải được dữ liệu thật. Cố ý KHÔNG dựng danh sách tỉnh/huyện
 * đầy đủ: bản đồ hành chính Việt Nam vừa thay đổi lớn, một danh sách sai còn
 * tệ hơn không có danh sách.
 */

import { useEffect, useRef, useState } from "react";
import { searchPlace, type PlaceHit } from "@/lib/api";

// 16 điểm đã kiểm chứng — cùng bộ dùng để huấn luyện mô hình khí hậu.
const QUICK: { name: string; lat: number; lon: number; note: string }[] = [
  { name: "Bến Tre", lat: 10.24, lon: 106.37, note: "đồng bằng sông Cửu Long" },
  { name: "Cà Mau", lat: 9.18, lon: 105.15, note: "cực Nam, ngập mặn" },
  { name: "Trà Leng, Quảng Nam", lat: 15.33, lon: 108.05, note: "núi dốc, từng sạt lở" },
  { name: "Huế", lat: 16.46, lon: 107.59, note: "mưa lớn, từng lũ lịch sử" },
  { name: "Phan Rang", lat: 11.56, lon: 108.99, note: "khô hạn nhất nước" },
  { name: "Buôn Ma Thuột", lat: 12.67, lon: 108.05, note: "cao nguyên bazan" },
  { name: "Hà Nội", lat: 21.03, lon: 105.85, note: "đồng bằng Bắc Bộ" },
  { name: "Lai Châu", lat: 22.4, lon: 103.47, note: "núi cao Tây Bắc" },
];

export default function Start({
  onPick,
  onStory,
}: {
  onPick: (lat: number, lon: number, label?: string) => void;
  onStory?: () => void;
}) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<PlaceHit[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [locating, setLocating] = useState(false);
  const [geoErr, setGeoErr] = useState<string | null>(null);
  const [coordStr, setCoordStr] = useState("");
  const [coordErr, setCoordErr] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Dán toạ độ GPS trực tiếp — cho người biết chính xác lat/lon (vd copy từ
  // Google Maps). Nhận "21.03, 105.85", "21.03 105.85", hay có ký hiệu độ.
  function goCoord() {
    setCoordErr(null);
    const nums = coordStr.replace(/[^\d.,\-\s]/g, " ").match(/-?\d+(\.\d+)?/g);
    if (!nums || nums.length < 2) {
      setCoordErr("Nhập dạng: vĩ độ, kinh độ — vd 21.0278, 105.8342");
      return;
    }
    const lat = parseFloat(nums[0]);
    const lon = parseFloat(nums[1]);
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      setCoordErr("Toạ độ không hợp lệ (vĩ độ ≤ 90, kinh độ ≤ 180).");
      return;
    }
    onPick(lat, lon, `Toạ độ ${lat.toFixed(4)}, ${lon.toFixed(4)}`);
  }

  // Chờ người dùng ngừng gõ rồi mới hỏi. Nominatim giới hạn 1 lần/giây, gọi
  // theo từng phím là vừa vi phạm chính sách vừa chậm.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const s = q.trim();
    if (s.length < 2) {
      setHits([]);
      setMsg(null);
      return;
    }
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await searchPlace(s);
        setHits(r.results);
        setMsg(r.results.length ? null : r.message ?? null);
      } catch {
        setHits([]);
        setMsg("Chưa tìm được — bạn có thể bấm thẳng lên bản đồ.");
      } finally {
        setBusy(false);
      }
    }, 600);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [q]);

  function locate() {
    setGeoErr(null);
    if (!navigator.geolocation) {
      setGeoErr("Thiết bị này không hỗ trợ định vị. Bấm thẳng lên bản đồ nhé.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating(false);
        onPick(p.coords.latitude, p.coords.longitude, "Vị trí của bạn");
      },
      (e) => {
        setLocating(false);
        setGeoErr(
          e.code === e.PERMISSION_DENIED
            ? "Bạn chưa cho phép truy cập vị trí. Gõ tên xã hoặc bấm bản đồ cũng được."
            : "Chưa lấy được vị trí. Gõ tên xã hoặc bấm bản đồ cũng được.",
        );
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  }

  return (
    <div className="start">
      <h2 className="start-h">Thửa đất của bạn ở đâu?</h2>
      <p className="start-sub">
        Chọn một chỗ, TerraTwin sẽ kiểm tra <b>toàn bộ rủi ro trong 7 ngày tới</b>{" "}
        và cho biết nên làm gì. Mất khoảng ba giây.
      </p>

      {onStory && (
        <button className="start-story" onClick={onStory}>
          ▶ Xem nhanh 90 giây — TerraTwin làm được gì
          <small>Câu chuyện thật: lũ Huế 2020, có bằng chứng backtest</small>
        </button>
      )}

      <button className="start-gps" onClick={locate} disabled={locating}>
        {locating ? "Đang xác định vị trí…" : "📍 Dùng vị trí của tôi"}
        <small>Chính xác nhất nếu bạn đang đứng trên thửa đất</small>
      </button>
      {geoErr && <p className="start-warn">{geoErr}</p>}

      <div className="start-or"><span>hoặc</span></div>

      <input
        className="start-q"
        placeholder="Gõ tên xã, huyện… vd. Ba Tri"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoComplete="off"
      />
      {busy && <p className="start-note">Đang tìm…</p>}
      {msg && <p className="start-warn">{msg}</p>}
      {hits.length > 0 && (
        <ul className="start-hits">
          {hits.map((h, i) => (
            <li key={i}>
              <button onClick={() => onPick(h.lat, h.lon, h.label)}>
                {h.label}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="start-or"><span>hoặc dán toạ độ GPS</span></div>

      <div className="start-coord">
        <input
          className="start-q"
          placeholder="vd. 21.0278, 105.8342 (copy từ Google Maps)"
          value={coordStr}
          onChange={(e) => setCoordStr(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") goCoord();
          }}
          inputMode="decimal"
          autoComplete="off"
        />
        <button onClick={goCoord} disabled={!coordStr.trim()}>Đi tới</button>
      </div>
      {coordErr && <p className="start-warn">{coordErr}</p>}

      <div className="start-or"><span>hoặc thử một nơi có sẵn</span></div>

      <div className="start-quick">
        {QUICK.map((p) => (
          <button key={p.name} onClick={() => onPick(p.lat, p.lon, p.name)}>
            <b>{p.name}</b>
            <small>{p.note}</small>
          </button>
        ))}
      </div>

      <p className="start-foot">
        Bạn cũng có thể <b>bấm thẳng vào bản đồ</b> — hoặc vẽ một vùng để tính
        theo cả thửa.
      </p>
    </div>
  );
}
