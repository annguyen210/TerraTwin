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
import { useLang } from "@/lib/i18n";
import { CirclePlay, MapPin } from "lucide-react";
import { findCoordInText, inVietnam, isListingSite, looksLikeUrl, outsideMessage, parseCoord, parseMapLink } from "@/lib/geo";
import { saveListingDraft } from "@/lib/listingDraft";

// 16 điểm đã kiểm chứng — cùng bộ dùng để huấn luyện mô hình khí hậu.
// ĐẤT NÔNG NGHIỆP / ven đô, nơi radar đọc được (17/10/2026): trước đây 7/8 điểm là TRUNG TÂM thành phố (WorldCover xây
// dựng 63–99,8%) nên lịch sử nước đều "0 đợt" — radar không thấy ngập giữa nhà. Chọn bằng số đo WorldCover trong khung
// radar 200 m + lịch sử nước thật; ưu tiên điểm có đợt nước rơi vào mùa lũ, không phải lịch cho nước vào ruộng.
// Giữ backend/app/services/demo_plots.py và backend/app/warm.py khớp danh sách này.
const QUICK: { name: string; lat: number; lon: number; note: string; note_en: string }[] = [
  { name: "Bến Tre", lat: 10.07, lon: 106.57, note: "ruộng lúa, đồng bằng sông Cửu Long", note_en: "rice fields, Mekong Delta" },
  { name: "Cà Mau", lat: 9.18, lon: 105.09, note: "ruộng lúa–tôm, cực Nam ngập mặn", note_en: "rice–shrimp fields, saline south" },
  { name: "Trà Leng, Quảng Nam", lat: 15.33, lon: 108.05, note: "rừng núi dốc, từng sạt lở", note_en: "steep forested hills, past landslide" },
  { name: "Huế", lat: 16.52, lon: 107.59, note: "đồng lúa, mùa lũ tháng 10–1 (ERA5)", note_en: "rice fields, Oct–Jan flood season (ERA5)" },
  { name: "Phan Rang", lat: 11.56, lon: 108.93, note: "ruộng ở vùng khô hạn nhất nước", note_en: "fields in the driest region" },
  { name: "Buôn Ma Thuột", lat: 12.73, lon: 108.05, note: "vườn cà phê, cao nguyên bazan", note_en: "coffee farms, basalt highlands" },
  { name: "Hà Nội", lat: 21.12, lon: 105.89, note: "ruộng ven đô, đồng bằng Bắc Bộ", note_en: "peri-urban rice, Red River Delta" },
  { name: "Lai Châu", lat: 22.36, lon: 103.59, note: "nương ruộng núi cao Tây Bắc", note_en: "upland fields, high NW mountains" },
];

export default function Start({
  onPick,
  onStory,
}: {
  onPick: (lat: number, lon: number, label?: string) => void;
  onStory?: () => void;
}) {
  const { t } = useLang();
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
  //
  // TỰ NHẬN DIỆN NHẦM THỨ TỰ: rất nhiều người dán kinh độ trước (105.85, 21.03).
  // Nếu (lat,lon) ngoài khung Việt Nam nhưng đảo lại thì vào → tự hoán đổi và
  // báo nhẹ, thay vì bắt người dùng tự đoán "vĩ độ hay kinh độ trước".
  function goCoord() {
    setCoordErr(null);
    const c = parseCoord(coordStr);
    if (!c) {
      setCoordErr(linkProblem(coordStr) ?? t("Nhập dạng: vĩ độ, kinh độ — vd 21.0278, 105.8342 (hoặc 21°01'40\"N 105°50'03\"E), hoặc dán link Google Maps.",
                                             "Use: latitude, longitude — e.g. 21.0278, 105.8342 (or 21°01'40\"N 105°50'03\"E), or paste a Google Maps link."));
      return;
    }
    if (!inVietnam(c.lat, c.lon)) {
      setCoordErr(Math.abs(c.lat) > 90 || Math.abs(c.lon) > 180
        ? t("Toạ độ không hợp lệ (vĩ độ ≤ 90, kinh độ ≤ 180).", "Invalid coordinates (latitude ≤ 90, longitude ≤ 180).")
        : outsideMessage(c.lat, c.lon));
      return;
    }
    onPick(c.lat, c.lon, coordLabel(c));
  }

  function coordLabel(c: { lat: number; lon: number; swapped: boolean; source?: string }) {
    const where = c.source ? t(` (${c.source})`, c.source === "trong nội dung" ? " (in the text)" : ` (${c.source})`) : "";
    return t(`Toạ độ ${c.lat.toFixed(4)}, ${c.lon.toFixed(4)}`, `Coordinates ${c.lat.toFixed(4)}, ${c.lon.toFixed(4)}`) + where
      + (c.swapped ? t(" (đã tự sửa thứ tự)", " (order fixed)") : "");
  }

  /** Link không dùng được → lời giải thích (null nếu không phải link). Không tải trang nào. */
  function linkProblem(s: string): string | null {
    if (!looksLikeUrl(s)) return null;
    if (isListingSite(s)) return t("TerraTwin không tải nội dung trang rao bất động sản. Chép phần CHỮ của tin rồi dán vào ô tìm kiếm phía trên: nếu tin có toạ độ hoặc link bản đồ thì dùng luôn, nội dung được giữ sẵn để đối chiếu ở tab Kiểm chứng.",
                                   "TerraTwin doesn't download real-estate listing pages. Copy the listing TEXT and paste it in the search box above: coordinates or a map link inside are used directly, and the text is kept ready for the Check tab.");
    const m = parseMapLink(s);
    if (m && "short" in m) return t("Link rút gọn (maps.app.goo.gl) không chứa toạ độ. Mở link, nhấn giữ vào ghim để hiện toạ độ rồi chép vào đây — hoặc dán link đầy đủ từ thanh địa chỉ trình duyệt.",
                                    "Short links (maps.app.goo.gl) carry no coordinates. Open it, long-press the pin to show the coordinates and copy them here — or paste the full link from the browser address bar.");
    return t("Link này không có toạ độ. Dán link Google Maps / OpenStreetMap có vị trí, hoặc toạ độ.",
             "This link has no coordinates. Paste a Google Maps / OpenStreetMap link with a location, or coordinates.");
  }

  // Chờ người dùng ngừng gõ rồi mới hỏi. Nominatim giới hạn 1 lần/giây, gọi
  // theo từng phím là vừa vi phạm chính sách vừa chậm.
  //
  // KHÔNG gửi Nominatim những thứ không phải địa danh (17/10/2026): link bản đồ → đọc toạ độ trong link; toạ độ gõ
  // vào ô này → dùng luôn; đoạn chữ dài (nội dung tin đăng dán vào) → tìm toạ độ trong tin + giữ nội dung cho tab
  // Kiểm chứng. Không tải trang nào, không lưu tin lên máy chủ.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    const s = q.trim();
    if (s.length < 2) {
      setHits([]);
      setMsg(null);
      return;
    }
    const asHit = (c: { lat: number; lon: number; swapped: boolean; source?: string }) =>
      ({ label: coordLabel(c), lat: c.lat, lon: c.lon, kind: "coord" });
    if (looksLikeUrl(s)) {
      const c = isListingSite(s) ? null : parseCoord(s);
      if (c && inVietnam(c.lat, c.lon)) { setHits([asHit(c)]); setMsg(null); }
      else { setHits([]); setMsg(c ? outsideMessage(c.lat, c.lon) : linkProblem(s)); }
      return;
    }
    if (s.length >= 80) {
      saveListingDraft(s);
      const c = findCoordInText(s);
      setHits(c ? [asHit(c)] : []);
      setMsg(c ? t("Đã giữ nội dung tin — chọn toạ độ dưới đây rồi mở tab Kiểm chứng để đối chiếu từng câu với số đo.",
                   "Listing text kept — pick the coordinates below, then open the Check tab to compare each claim with measurements.")
               : t("Có vẻ đây là nội dung tin đăng: đã giữ sẵn để kiểm. Tin không ghi toạ độ — chọn thửa (bấm bản đồ, định vị, hoặc gõ tên xã) rồi mở tab Kiểm chứng.",
                   "This looks like listing text: kept ready to check. It has no coordinates — pick the plot (tap the map, locate, or type the commune), then open the Check tab."));
      return;
    }
    if (/^\s*-?\d/.test(s)) {
      const c = parseCoord(s);
      if (c && inVietnam(c.lat, c.lon)) { setHits([asHit(c)]); setMsg(null); return; }
    }
    timer.current = setTimeout(async () => {
      setBusy(true);
      try {
        const r = await searchPlace(s);
        setHits(r.results);
        setMsg(r.results.length ? null : r.message ?? null);
      } catch {
        setHits([]);
        setMsg(t("Chưa tìm được — bạn có thể bấm thẳng lên bản đồ.", "Not found — you can tap the map directly."));
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
      setGeoErr(t("Thiết bị này không hỗ trợ định vị. Bấm thẳng lên bản đồ nhé.", "This device can't locate you. Tap the map instead."));
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating(false);
        const { latitude: la, longitude: lo, accuracy } = p.coords;
        // Máy tính không có GPS: trình duyệt ĐOÁN theo mạng — có thể ra nước khác (mạng
        // trường, VPN) hoặc lệch nhiều km. Không gửi toạ độ ngoài Việt Nam đi; sai số lớn
        // thì nói rõ để người dùng kéo bản đồ cho đúng thửa trước khi tin kết quả.
        if (!inVietnam(la, lo)) {
          setGeoErr(outsideMessage(la, lo, "gps"));
          return;
        }
        const km = accuracy ? accuracy / 1000 : 0;
        onPick(la, lo, km > 1.5
          ? t(`Vị trí ƯỚC LƯỢNG theo mạng (sai số ~${km.toFixed(0)} km) — kéo bản đồ cho đúng thửa rồi bấm phân tích ô ngắm`,
              `Network-ESTIMATED location (~${km.toFixed(0)} km error) — drag the map onto the plot, then analyse the crosshair`)
          : t("Vị trí của bạn", "Your location"));
      },
      (e) => {
        setLocating(false);
        setGeoErr(
          e.code === e.PERMISSION_DENIED
            ? t("Bạn chưa cho phép truy cập vị trí. Gõ tên xã hoặc bấm bản đồ cũng được.", "Location permission was denied. Type a commune or tap the map instead.")
            : t("Chưa lấy được vị trí. Gõ tên xã hoặc bấm bản đồ cũng được.", "Couldn't get your location. Type a commune or tap the map instead."),
        );
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  }

  return (
    <div className="start">
      <h2 className="start-h">{t("Thửa đất của bạn ở đâu?", "Where is your plot?")}</h2>
      <p className="start-sub">
        {t("Chọn một chỗ: ", "Pick a spot: ")}
        <b>{t("lịch sử nước radar, loại đất, hiểm hoạ 10 năm, kiểm tin đăng", "radar water history, land cover, 10-year hazards, listing check")}</b>{" "}
        {t("và hồ sơ ký số — chọn tab mở sẵn ở trên.", "and a signed dossier — choose the tab to open above.")}
      </p>

      {onStory && (
        <button className="start-story" onClick={onStory}>
          <CirclePlay size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {t("Xem nhanh 90 giây — TerraTwin làm được gì", "90-second tour — what TerraTwin does")}
          <small>{t("Câu chuyện thật: lũ Huế 2020, có bằng chứng backtest",
                     "A real story: the 2020 Huế flood, backtested")}</small>
        </button>
      )}

      <button className="start-gps" onClick={locate} disabled={locating}>
        <MapPin size={16} strokeWidth={1.9} aria-hidden="true" className="ui-ic" /> {locating ? t("Đang xác định vị trí…", "Locating…") : t("Dùng vị trí của tôi", "Use my location")}
        <small>{t("Chính xác nhất nếu bạn đang đứng trên thửa đất",
                   "Most accurate if you're standing on the plot")}</small>
      </button>
      {geoErr && <p className="start-warn">{geoErr}</p>}

      <div className="start-or"><span>{t("hoặc", "or")}</span></div>

      <input
        className="start-q"
        placeholder={t("Gõ tên xã, huyện… vd. Ba Tri — hoặc dán link Google Maps, nội dung tin đăng",
                       "Type a commune/district… e.g. Ba Tri — or paste a Google Maps link or listing text")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        autoComplete="off"
      />
      {busy && <p className="start-note">{t("Đang tìm…", "Searching…")}</p>}
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

      <div className="start-or"><span>{t("hoặc dán toạ độ GPS", "or paste GPS coordinates")}</span></div>

      <div className="start-coord">
        <input
          className="start-q"
          placeholder={t("vd. 21.0278, 105.8342 hoặc link Google Maps",
                          "e.g. 21.0278, 105.8342 or a Google Maps link")}
          value={coordStr}
          onChange={(e) => setCoordStr(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") goCoord();
          }}
          autoComplete="off"
        />
        <button onClick={goCoord} disabled={!coordStr.trim()}>{t("Đi tới", "Go")}</button>
      </div>
      {coordErr && <p className="start-warn">{coordErr}</p>}

      <div className="start-or"><span>{t("hoặc thử một nơi có sẵn", "or try a ready-made spot")}</span></div>

      <div className="start-quick">
        {QUICK.map((p) => (
          <button key={p.name} onClick={() => onPick(p.lat, p.lon, p.name)}>
            <b>{p.name}</b>
            <small>{t(p.note, p.note_en)}</small>
          </button>
        ))}
      </div>

      <p className="start-foot">
        {t("Bạn cũng có thể ", "You can also ")}
        <b>{t("bấm thẳng vào bản đồ", "click directly on the map")}</b>
        {t(" — hoặc vẽ một vùng để tính theo cả thửa.",
           " — or draw an area to compute over the whole plot.")}
      </p>
    </div>
  );
}
