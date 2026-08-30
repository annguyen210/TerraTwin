"use client";

/**
 * MỘT CÂU TRẢ LỜI, trước mọi thứ khác.
 *
 * VẤN ĐỀ ĐANG SỬA. Trước đây chọn một điểm thì thấy kết quả của ĐÚNG MỘT mô-đun
 * mà người dùng đã chọn từ trước — mà họ chọn lúc chưa biết mình cần gì. Quét
 * toàn cảnh 18 mũi nhọn trong 2,5 giây thì lại nằm sau một cái tab. Nghĩa là
 * thứ mạnh nhất của sản phẩm bị giấu, còn thứ hiện ra đầu tiên thì hẹp và dễ
 * sai. Người dùng kết luận "phần mềm chỉ có thế" — và họ kết luận đúng với thứ
 * họ được cho xem.
 *
 * Ở đây đảo lại: chọn chỗ xong là quét HẾT, rồi trả lời bằng một câu. Chi tiết
 * từng mô-đun tụt xuống dưới, dành cho ai muốn đào sâu.
 *
 * BA NGUYÊN TẮC VIẾT CÂU TRẢ LỜI:
 *
 * ① KHÔNG cộng gộp mọi mô-đun thành một điểm số rồi khoe. Người ta cần biết
 *    "sắp có chuyện gì", không cần biết "thửa này 72 điểm".
 * ② Câu đầu tiên phải trả lời được cho người CHƯA đọc gì phía dưới.
 * ③ Chỗ nào dữ liệu chưa đủ thì đếm riêng và nói ra, không trộn vào phần "an
 *    toàn". "Chưa biết" và "không sao" là hai chuyện khác hẳn nhau.
 */

import { useEffect, useRef, useState } from "react";
import { scanAll, type ScanResult, type ScanModule, type ModuleInfo } from "@/lib/api";
import Passport from "./Passport";
import PlotView from "./PlotView";
import WhyTrust from "./WhyTrust";

const TONE: Record<string, string> = {
  danger: "bad",
  warning: "warn",
  safe: "ok",
};

// Màu ô trong lưới toàn cảnh. Mục chưa có dữ liệu / đang chạy / ngoài phạm vi →
// "chờ" (xám), KHÔNG tô như an toàn — "chưa biết" khác "không sao".
function cellTone(m: ScanModule): string {
  if (m.status === "need_data" || m.status === "pending" || m.status === "out_of_scope")
    return "wait";
  return TONE[m.risk_level] ?? "wait";
}

function headline(d: ScanResult): { tone: string; big: string; sub: string } {
  const nguy = d.alerts.filter((a) => a.risk_level === "danger");
  const canh = d.alerts.filter((a) => a.risk_level === "warning");
  // BỐN TRẠNG THÁI, đếm riêng. Gộp lại là tự bôi xấu mình: một mục ĐANG CHẠY
  // và một mục KHÔNG CÓ DỮ LIỆU trông như nhau, còn "ở đây không áp dụng" thì
  // vốn là câu trả lời đúng chứ không phải lỗ hổng.
  const chuaBiet = d.modules.filter((m) => m.status === "need_data").length;

  const duoi = chuaBiet
    ? `${chuaBiet} mục chưa đủ dữ liệu để kết luận — xem bên dưới.`
    : "Mọi mục đều có dữ liệu thật để kết luận.";

  if (nguy.length) {
    return {
      tone: "bad",
      big:
        nguy.length === 1
          ? `Cần xử lý ngay: ${nguy[0].name.toLowerCase()}`
          : `Cần xử lý ngay: ${nguy.length} rủi ro`,
      sub: duoi,
    };
  }
  if (canh.length) {
    return {
      tone: "warn",
      big:
        canh.length === 1
          ? `Nên chú ý: ${canh[0].name.toLowerCase()}`
          : `Nên chú ý: ${canh.length} rủi ro`,
      sub: duoi,
    };
  }

  // KHÔNG được nói "chưa thấy rủi ro" khi phần lớn còn mù.
  //
  // Đo thật ở Bến Tre lúc nguồn dữ liệu đang bị chặn: 0 cảnh báo nhưng 7/16 mục
  // không kết luận được — kể cả xâm nhập mặn, thứ quan trọng nhất ở đúng chỗ
  // đó. Câu "bảy ngày tới chưa thấy rủi ro nào" khi ấy đọc như một lời trấn an,
  // trong khi sự thật là KHÔNG BIẾT. Đẩy cảnh báo xuống dòng phụ là chưa đủ:
  // người ta đọc dòng to rồi đóng app.
  const dung = d.modules.length - chuaBiet;
  if (chuaBiet > 0 && chuaBiet >= d.modules.length / 3) {
    return {
      tone: "warn",
      big: `Chưa kết luận được — ${chuaBiet}/${d.modules.length} mục thiếu dữ liệu`,
      sub:
        dung > 0
          ? `${dung} mục còn lại chưa thấy rủi ro. Phần thiếu không có nghĩa là an toàn.`
          : "Chưa mục nào có đủ dữ liệu thật để kết luận.",
    };
  }

  return {
    tone: "ok",
    big: "Bảy ngày tới chưa thấy rủi ro nào",
    sub: duoi,
  };
}

export default function Answer({
  lat,
  lon,
  area,
  label,
  modules,
  onSelectModule,
  onDetail,
  onRisk,
  onTerra,
}: {
  lat: number;
  lon: number;
  area?: number;
  label?: string;
  // Danh sách mũi nhọn để vẽ lưới skeleton NGAY khi đang quét — cho người dùng
  // thấy phần mềm đang kiểm cả 18 thứ, thay vì một vòng xoay câm 15 giây.
  modules?: ModuleInfo[];
  onSelectModule?: (id: string) => void;
  onDetail?: () => void;
  // Báo mức rủi ro cao nhất ra ngoài để bản đồ tô khung cùng màu — nối phần
  // lớn nhất của màn hình với câu trả lời, thay vì để nó là tấm nền trơn.
  onRisk?: (risk: string) => void;
  // Chuyển TerraScore ra ngoài. Lượt quét đã tính sẵn nó, nên trang không cần
  // gọi /api/terrascore lần nữa — đó chính là lời gọi thừa làm chậm gấp năm lần.
  onTerra?: (t: ScanResult["terrascore"]) => void;
}) {
  const [d, setD] = useState<ScanResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [giay, setGiay] = useState(0);
  const dong = useRef<ReturnType<typeof setInterval> | null>(null);

  // Đếm giây khi chờ. LÝ DO CÓ CÁI NÀY: đo thật cho thấy nơi đã có cache trả
  // lời trong 2,5 giây, nhưng nơi CHƯA TỪNG XEM mất tới 15 giây — vì phải tải
  // 10 năm lịch sử của đúng toạ độ đó về mới hiệu chuẩn được ngưỡng. Con số
  // 2,5 giây vẫn hay được nêu là trường hợp ĐÃ ẤM, không phải lần đầu.
  //
  // Mười lăm giây nhìn một vòng xoay câm là quá đủ để người ta đóng app. Không
  // giấu được thì nói ra: đang làm gì, vì sao lâu, và lần sau sẽ nhanh.
  useEffect(() => {
    if (!busy) {
      if (dong.current) clearInterval(dong.current);
      setGiay(0);
      return;
    }
    dong.current = setInterval(() => setGiay((g) => g + 1), 1000);
    return () => {
      if (dong.current) clearInterval(dong.current);
    };
  }, [busy]);

  useEffect(() => {
    let huy = false;
    setBusy(true);
    setErr(null);
    setD(null);
    scanAll(lat, lon, area)
      .then((r) => {
        if (huy) return;
        setD(r);
        // LƯỢT SÂU CHẠY NGAY SAU, ở nền. Bảy mũi nhọn cần ảnh vệ tinh mất 6–60
        // giây mỗi cái nên không thể để trong lượt nhanh. Nhưng bỏ mặc chúng ở
        // trạng thái "đang kiểm tra" thì chúng treo vĩnh viễn, và trông y hệt
        // như thiếu dữ liệu — đúng thứ làm người dùng thấy phần mềm sơ sài.
        // Gọi tiếp và thay kết quả vào khi xong.
        scanAll(lat, lon, area, true)
          .then((sau) => !huy && setD(sau))
          .catch(() => {});
      })
      .catch((e) => !huy && setErr(e.message))
      .finally(() => !huy && setBusy(false));
    return () => {
      huy = true;
    };
  }, [lat, lon, area]);

  useEffect(() => {
    if (!d || !onRisk) return;
    const co = d.alerts.some((a) => a.risk_level === "danger")
      ? "danger"
      : d.alerts.some((a) => a.risk_level === "warning")
        ? "warning"
        : "safe";
    onRisk(co);
  }, [d, onRisk]);

  useEffect(() => {
    if (d?.terrascore && onTerra) onTerra(d.terrascore);
  }, [d, onTerra]);

  if (busy) {
    return (
      <div className="ans">
        {label && <p className="ans-where">📍 {label}</p>}
        <div className="ans-scanning">
          <span className="ans-spin sm" />
          <b>Đang quét {modules?.length ?? 18} mũi nhọn cho thửa này{giay ? ` · ${giay}s` : ""}…</b>
        </div>
        {/* Lưới SỐNG: hiện ngay mọi mũi nhọn đang được kiểm (skeleton nhấp nháy),
            để 15 giây chờ trở thành bằng chứng phần mềm đang làm RẤT NHIỀU việc —
            thay vì một vòng xoay câm khiến người ta tưởng nó "sơ sài". */}
        {modules && modules.length > 0 && (
          <div className="ans-grid ans-grid-skel">
            {modules.map((m) => (
              <div key={m.id} className="ans-cell skel">
                <span className="ans-cell-ic">{m.icon}</span>
                <span className="ans-cell-nm">{m.name}</span>
                <span className="ans-cell-dot" />
              </div>
            ))}
          </div>
        )}
        {giay >= 4 && (
          <p className="ans-wait">
            Lần đầu xem một nơi mới thì lâu hơn — TerraTwin đang tải{" "}
            <b>10 năm lịch sử thời tiết của đúng toạ độ này</b> để biết thế nào
            mới là bất thường <i>ở đây</i>, thay vì dùng một ngưỡng chung cho cả
            nước. Lần sau chỗ này trả lời trong vài giây.
          </p>
        )}
      </div>
    );
  }

  if (err) {
    return (
      <div className="ans">
        <p className="ans-err">⚠️ {err}</p>
      </div>
    );
  }
  if (!d) return null;

  // Ngoài vùng phục vụ thì nói thẳng, không chấm điểm cho mặt nước.
  if (d.region && d.region.serviceable === false) {
    return (
      <div className="ans">
        <div className="ans-head off">
          <b>
            {d.region.kind === "sea"
              ? "🌊 Chỗ này là mặt nước"
              : "🗺️ Ngoài phạm vi phục vụ"}
          </b>
          <p>{d.region.note}</p>
        </div>
      </div>
    );
  }

  const h = headline(d);
  const canLam = d.alerts.filter((a) => a.recommendation);
  const chuaDu = d.modules.filter((m) => m.status === "need_data");
  const dangChay = d.modules.filter((m) => m.status === "pending");
  const khongApDung = d.modules.filter((m) => m.status === "out_of_scope");

  return (
    <div className="ans">
      {label && <p className="ans-where">📍 {label}</p>}

      {/* ẢNH ĐẶT TRƯỚC CHỮ. Người ta nhận ra mảnh đất của mình bằng mắt trong
          một giây; đọc một đoạn văn tả về nó thì mất lâu hơn và vẫn không chắc
          là đúng thửa. Thấy đúng chỗ rồi mới có lý do đọc tiếp. */}
      <PlotView lat={lat} lon={lon} />

      <div className={`ans-head ${h.tone}`}>
        <b>{h.big}</b>
        <p>{h.sub}</p>
      </div>

      {canLam.length > 0 && (
        <div className="ans-todo">
          <span className="ans-cap">Nên làm gì</span>
          {canLam.map((a) => (
            <div key={a.id} className={`ans-item ${TONE[a.risk_level] ?? ""}`}>
              <button className="ans-name" onClick={() => onSelectModule?.(a.id)}>
                {a.icon} {a.name}
              </button>
              <p className="ans-why">{a.headline}</p>
              <p className="ans-do">→ {a.recommendation}</p>
            </div>
          ))}
        </div>
      )}

      {canLam.length === 0 && (
        <p className="ans-calm">
          Không có việc gì cần làm gấp. Bật cảnh báo để TerraTwin tự báo khi
          tình hình đổi, thay vì bạn phải mở lên xem.
        </p>
      )}

      {/* TOÀN CẢNH 1 MẮT: cho thấy phần mềm vừa kiểm CẢ 18 mũi nhọn, không phải
          chỉ một kết luận. Đây là thứ chữa trực tiếp cảm giác "sơ sài" — breadth
          hiện ngay, không cần đổi tab. Bấm ô nào là nhảy vào chi tiết mục đó. */}
      {d.modules.length > 0 && (
        <div className="ans-grid-wrap">
          <span className="ans-cap">
            Đã quét toàn bộ {d.modules.length} mũi nhọn cho thửa này
          </span>
          <div className="ans-grid">
            {d.modules.map((m) => (
              <button
                key={m.id}
                className={`ans-cell ${cellTone(m)}`}
                title={`${m.name}: ${m.headline}`}
                onClick={() => onSelectModule?.(m.id)}
              >
                <span className="ans-cell-ic">{m.icon}</span>
                <span className="ans-cell-nm">{m.name}</span>
                <span className="ans-cell-dot" />
              </button>
            ))}
          </div>
          <div className="ans-grid-key">
            <span><i className="k-bad" /> nguy hiểm</span>
            <span><i className="k-warn" /> cảnh báo</span>
            <span><i className="k-ok" /> an toàn</span>
            <span><i className="k-wait" /> đang/ chờ dữ liệu</span>
          </div>
        </div>
      )}

      {dangChay.length > 0 && (
        <div className="ans-pending">
          <span className="ans-spin sm" />
          <div>
            <b>Đang kiểm tra thêm {dangChay.length} mục</b>
            <p>
              Những mục này cần ảnh vệ tinh nên lâu hơn hẳn — chúng đang chạy
              nền, không phải thiếu dữ liệu. Mở{" "}
              <i>{dangChay.slice(0, 3).map((m) => m.name.toLowerCase()).join(", ")}</i>
              {dangChay.length > 3 ? "…" : ""} ở cột trái để xem từng cái.
            </p>
          </div>
        </div>
      )}

      {khongApDung.length > 0 && (
        <p className="ans-na">
          {khongApDung.length} mục <b>không áp dụng</b> ở đây (
          {khongApDung.map((m) => m.name.toLowerCase()).join(", ")}) — đó là câu
          trả lời đúng cho vị trí này, không phải thiếu sót.
        </p>
      )}

      {chuaDu.length > 0 && (
        <details className="ans-unknown">
          <summary>
            {chuaDu.length} mục chưa đủ dữ liệu để kết luận
          </summary>
          <p className="ans-note">
            Những mục này <b>không phải là an toàn</b> — chỉ là chưa có đủ dữ
            liệu thật để nói. Phần lớn chờ kết nối ảnh vệ tinh Sentinel-2.
          </p>
          <ul>
            {chuaDu.map((m) => (
              <li key={m.id}>
                {m.icon} {m.name} — {m.headline}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Hồ sơ riêng đặt TRƯỚC khối đối chiếu: nó trả lời "phần mềm này hơn
          app thời tiết ở chỗ nào" bằng ba con số cụ thể của chính thửa này,
          còn khối đối chiếu trả lời "vì sao tin được con số đó". */}
      <Passport lat={lat} lon={lon} />

      <WhyTrust lat={lat} lon={lon} />

      <div className="ans-more">
        <button onClick={onDetail}>Xem chi tiết từng mục</button>
        <span className="ans-src">
          {Math.round((d.real_data_ratio ?? 0) * 100)}% kết luận dựa trên dữ liệu đo được
        </span>
      </div>
    </div>
  );
}
