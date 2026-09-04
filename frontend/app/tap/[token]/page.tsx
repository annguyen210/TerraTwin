"use client";

/**
 * MỘT CHẠM — trang công khai mở từ link trong tin cảnh báo (Zalo/email).
 *
 * VÌ SAO TỒN TẠI. Kho quan sát thực địa là tài sản duy nhất của TerraTwin không
 * tải được từ vệ tinh. Nhưng bắt người nông dân đăng nhập trước khi họ được nói
 * "ruộng tôi có ngập" là điểm chết của cả vòng lặp. Trang này bỏ hẳn rào đó:
 * mở link → thấy đúng MỘT câu hỏi → ba nút → xong. Không đăng nhập, không app.
 *
 * Bảo mật nằm ở token ký số trong URL (xem onetap.py), không ở phiên đăng nhập.
 * Trang cố ý ĐƠN GIẢN TỚI MỨC TỐI ĐA: một câu, ba nút, chữ to, bấm được bằng
 * ngón cái trên điện thoại yếu sóng.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  getTapQuestion,
  sendTapAnswer,
  type TapQuestion,
} from "@/lib/api";

export default function TapPage() {
  const params = useParams();
  const token = Array.isArray(params.token) ? params.token[0] : (params.token ?? "");

  const [q, setQ] = useState<TapQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [sending, setSending] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    if (!token) {
      setErr("Thiếu mã liên kết.");
      setLoading(false);
      return;
    }
    getTapQuestion(token)
      .then((d) => {
        if (!live) return;
        setQ(d);
        setLoading(false);
        if (d.answered) {
          setDone(
            d.outcome === "hit"
              ? "Bác đã xác nhận là CÓ xảy ra. Cảm ơn bác!"
              : d.outcome === "false_alarm"
              ? "Bác đã xác nhận là KHÔNG xảy ra. Cảm ơn bác!"
              : "Câu trả lời trước của bác đã được ghi nhận. Cảm ơn bác!",
          );
        }
      })
      .catch((e) => {
        if (!live) return;
        setErr(e.message);
        setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [token]);

  async function pick(value: "yes" | "no" | "unsure") {
    if (sending || done) return;
    setSending(value);
    try {
      const res = await sendTapAnswer(token, value);
      setDone(res.message);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSending(null);
    }
  }

  return (
    <div className="tap">
      <div className="tap-card">
        <div className="tap-brand">◵ TerraTwin</div>

        {loading && <p className="tap-load">Đang mở câu hỏi…</p>}

        {err && !loading && (
          <div className="tap-err">
            <div className="tap-emoji">🔗</div>
            <p>{err}</p>
            <a className="tap-home" href="/">Mở TerraTwin</a>
          </div>
        )}

        {q && !loading && !err && (
          <>
            {done ? (
              <div className="tap-thanks">
                <div className="tap-emoji">✅</div>
                <p className="tap-thanks-msg">{done}</p>
                <p className="tap-why">{q.why}</p>
                <a className="tap-home" href="/">Xem thửa của bạn trên TerraTwin</a>
              </div>
            ) : (
              <>
                <p className="tap-q">{q.question}</p>
                <div className="tap-btns">
                  {q.options.map((o) => (
                    <button
                      key={o.value}
                      className={`tap-btn tap-${o.value}`}
                      disabled={!!sending}
                      onClick={() => pick(o.value)}
                    >
                      {sending === o.value ? "Đang gửi…" : o.label}
                    </button>
                  ))}
                </div>
                <p className="tap-why">{q.why}</p>
              </>
            )}
          </>
        )}
      </div>
      <p className="tap-foot">Câu trả lời của bạn giúp chỉnh ngưỡng cảnh báo cho cả vùng — ẩn danh.</p>
    </div>
  );
}
