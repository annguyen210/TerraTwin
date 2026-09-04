"use client";

/**
 * TRANG ĐÓN (landing) — hiện khi CHƯA chọn thửa.
 *
 * VÌ SAO. Bố cục 3 cột (list trái + bản đồ + panel phải) hợp cho lúc ĐANG dùng,
 * nhưng lúc mới vào thì hai cột hẹp trông chật và thiếu chuyên nghiệp. Ở đây tách
 * hẳn: một trang rộng, phân mục rõ ràng, dẫn người dùng vào bằng đúng một hành
 * động — "đất của bạn ở đâu". Chọn xong mới lộ ra app làm việc (bản đồ + kết quả).
 *
 * Tái dùng toàn bộ logic nhập đã có (Start: tìm / GPS / toạ độ / nơi gợi ý;
 * MyLand: thửa đã lưu) — không viết lại, chỉ đặt trong một bố cục rộng đẹp hơn.
 */

import { useEffect, useState } from "react";

import Account from "./Account";
import MyLand from "./MyLand";
import Scorecard from "./Scorecard";
import Start from "./Start";
import { getScorecard, type AuthUser, type ModuleInfo,
         type Scorecard as SC } from "@/lib/api";

const FEATURES = [
  {
    icon: "🎯",
    title: "Hiệu chuẩn tới TỪNG THỬA",
    body: "Ngưỡng cảnh báo so với khí hậu 10 năm của chính điểm đó — báo động giả tụt từ 46–61% xuống ~3%. Không ai làm được điều này bằng một ngưỡng chung cho cả nước.",
  },
  {
    icon: "🔬",
    title: "Báo trước CÓ BẰNG CHỨNG",
    body: "Kiểm chứng trên thiên tai thật (lũ Huế 2020, sạt lở Trà Leng…): báo trước mấy ngày, kèm tỉ lệ báo bừa — không phải lời hứa suông.",
  },
  {
    icon: "🛰️",
    title: "Ảnh vệ tinh THẬT",
    body: "Nhìn thấy chính mảnh đất của bạn từ Sentinel-2 (Microsoft Planetary Computer) — không cần đăng ký khoá nào.",
  },
  {
    icon: "🛡️",
    title: "Tự canh đất cho bạn",
    body: "Lưu thửa → TerraTwin tự quét nền và báo TRƯỚC khi có rủi ro, qua Zalo/email — bạn không cần nhớ mở.",
  },
];

export default function Landing({
  user,
  onAuth,
  onStart,
  onStory,
  onLoad,
  onWorkspace,
  modules,
}: {
  user: AuthUser | null;
  onAuth: (u: AuthUser | null) => void;
  onStart: (lat: number, lon: number, label?: string) => void;
  onStory: () => void;
  onLoad: (lat: number, lon: number) => void;
  onWorkspace: () => void;
  modules: ModuleInfo[];
}) {
  const nModules = modules.length || 18;

  // SỐ LIỆU SỔ ĐIỂM LẤY MỘT LẦN Ở ĐÂY, dùng cho cả ô thống kê hero lẫn khối sổ
  // điểm bên dưới.
  //
  // VÌ SAO PHẢI GỘP: ô hero trước đây ghi cứng "~3% tỉ lệ báo bừa" — con số
  // THẬT, đo trên backtest các thiên tai lịch sử. Nhưng khi khối sổ điểm tự
  // chấm nằm ngay bên dưới và nói một tỉ lệ khác (đo trên cảnh báo đang chạy,
  // cơ sở đo khác hẳn), hai con số mâu thuẫn nhau trên cùng một màn hình. Người
  // xem không thể biết nên tin cái nào, và cái mất đi không phải là một con số
  // — mà là lòng tin vào cả hai.
  //
  // Nên: có đủ mẫu đo thật thì hero hiện SỐ ĐO THẬT; chưa đủ thì vẫn hiện con
  // số backtest nhưng ghi rõ cơ sở đo là backtest.
  const [sc, setSc] = useState<SC | null>(null);
  useEffect(() => {
    let live = true;
    getScorecard(90)
      .then((r) => live && setSc(r))
      .catch(() => {});          // hỏng thì hero lùi về số backtest, không sao
    return () => {
      live = false;
    };
  }, []);
  const doThat = sc?.enough && sc.far_pct !== null;

  return (
    <div className="lp">
      {/* Thanh trên cùng */}
      <header className="lp-top">
        <div className="lp-brand">◵ TerraTwin</div>
        <div className="lp-top-actions">
          <button className="lp-ws" onClick={onWorkspace}>⚙️ Khu làm việc</button>
          <Account user={user} onAuth={onAuth} />
        </div>
      </header>

      <div className="lp-body">
        {/* HERO + ô nhập */}
        <section className="lp-hero">
          <div className="lp-hero-txt">
            <span className="lp-eyebrow">Bản sao số của đất đai Việt Nam</span>
            <h1 className="lp-h1">
              Biết trước điều gì sắp xảy ra với <span>mảnh đất của bạn</span>
            </h1>
            <p className="lp-lede">
              Chọn đúng thửa của bạn — TerraTwin kiểm <b>toàn bộ rủi ro 7 ngày tới</b>{" "}
              bằng dữ liệu vệ tinh & khí hậu thật, hiệu chuẩn riêng cho chính chỗ
              đó, rồi cho biết <b>nên làm gì</b>.
            </p>
            <div className="lp-stats">
              <div><b>{nModules}</b><span>mũi nhọn</span></div>
              <div><b>12/12</b><span>ngành</span></div>
              <div title={doThat
                ? "Đo trên chính những cảnh báo TerraTwin đã phát trong 90 ngày qua."
                : "Đo trên backtest các thiên tai lịch sử. Sổ điểm chạy thật sẽ thay chỗ này khi đủ mẫu."}>
                <b>{doThat ? `${sc!.far_pct}%` : "~3%"}</b>
                <span>{doThat ? "báo bừa · đo thật" : "báo bừa · backtest"}</span>
              </div>
              <div><b>0đ</b><span>miễn phí dùng thử</span></div>
            </div>
          </div>

          <div className="lp-entry">
            {user && <MyLand user={user} onOpen={onStart} />}
            <Start onPick={onStart} onStory={onStory} />
          </div>
        </section>

        {/* SỔ ĐIỂM TỰ CHẤM.
            Đặt NGAY DƯỚI hero, trước cả phần "vì sao khác biệt", là có chủ ý:
            danh sách tính năng thì phần mềm nào cũng viết được, còn một sổ điểm
            công khai kèm cả tỉ lệ báo bừa lẫn số lần bỏ sót thì không ai dám
            bịa. Đây là câu trả lời nhanh nhất cho "phần mềm này hơn ở đâu". */}
        <section className="lp-score">
          <Scorecard data={sc} />
        </section>

        {/* VÌ SAO KHÁC BIỆT */}
        <section className="lp-why">
          <h2 className="lp-sec-h">Vì sao TerraTwin, không phải app thời tiết</h2>
          <div className="lp-feats">
            {FEATURES.map((f) => (
              <div className="lp-feat" key={f.title}>
                <span className="lp-feat-ic">{f.icon}</span>
                <b>{f.title}</b>
                <p>{f.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* DẢI DỮ LIỆU THẬT */}
        <section className="lp-trust">
          <span className="lp-trust-cap">Chạy trên dữ liệu THẬT, kiểm chứng được</span>
          <div className="lp-sources">
            {["Open-Meteo", "ERA5", "GloFAS", "NASA POWER", "Sentinel-2", "OpenStreetMap"].map((s) => (
              <span key={s}>{s}</span>
            ))}
          </div>
          <p className="lp-honest">
            Mỗi kết luận gắn cờ 🛰️ <b>đo được</b> hay 🧪 <b>ước lượng</b>, kèm khoảng
            tin cậy. Chỗ nào chưa đủ dữ liệu thì nói thẳng — không bịa số.
          </p>
        </section>

        <footer className="lp-foot">
          ◵ TerraTwin · {nModules} mũi nhọn · 12 ngành · dữ liệu thật, hiệu chuẩn từng thửa
        </footer>
      </div>
    </div>
  );
}
