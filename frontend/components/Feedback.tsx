"use client";

/**
 * U04 vòng khép kín + S05 quan sát thực địa — CÔNG TẮC KHỞI ĐỘNG CỦA CẢ MOAT.
 *
 * Đây là component quan trọng nhất trong toàn bộ phần mềm xét về dài hạn, và
 * cũng là thứ dễ bị bỏ quên nhất vì nó không "trông ngầu". Không có nó thì:
 *   S05 Federated không có gì để tổng hợp  → bảng hiệu chỉnh mãi rỗng
 *   S09 Model Engine không có gì để chấm    → không biết mô hình đúng hay sai
 *   U04 vòng khép kín không bao giờ khép
 *   Và lời hứa "càng dùng càng chính xác cho đất Việt" mãi chỉ là lời hứa.
 *
 * Vì vậy form được giữ ngắn hết mức: một người đang đứng ngoài ruộng, nắng,
 * dùng điện thoại. Hai câu hỏi, ba cái bấm, xong.
 */

import { useCallback, useEffect, useState } from "react";
import {
  addObservation,
  listActions,
  logAction,
  recordOutcome,
  type ActionRow,
  type AuthUser,
} from "@/lib/api";

const OUTCOMES = [
  { id: "avoided", label: "Tránh được thiệt hại" },
  { id: "reduced", label: "Giảm bớt thiệt hại" },
  { id: "no_effect", label: "Không thay đổi gì" },
  { id: "too_late", label: "Biết quá muộn" },
];

const SEVERITY = [
  { id: "nhe", label: "Nhẹ" },
  { id: "vua", label: "Vừa" },
  { id: "nang", label: "Nặng" },
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function Feedback({
  moduleId,
  moduleName,
  recommendation,
  lat,
  lon,
  user,
}: {
  moduleId: string;
  moduleName: string;
  recommendation: string;
  lat: number;
  lon: number;
  user: AuthUser | null;
}) {
  const [pending, setPending] = useState<ActionRow[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [obsOpen, setObsOpen] = useState(false);
  const [obsDate, setObsDate] = useState(today());
  const [severity, setSeverity] = useState("vua");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    if (!user) return;
    try {
      const all = await listActions();
      setPending(all.filter((a) => a.outcome === null));
    } catch {
      /* nhật ký hỏng không được chặn việc gửi quan sát mới */
    }
  }, [user]);

  useEffect(() => {
    load();
  }, [load]);

  async function markDone() {
    setBusy(true);
    setErr(null);
    try {
      await logAction(moduleId, recommendation, today());
      setMsg("Đã ghi. Vài ngày nữa quay lại cho biết kết quả nhé.");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function outcome(id: number, o: string) {
    setBusy(true);
    setErr(null);
    try {
      await recordOutcome(id, o);
      setMsg("Cảm ơn — kết quả này được dùng để chấm lại mô hình.");
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendObs(happened: boolean) {
    setBusy(true);
    setErr(null);
    try {
      await addObservation(
        lat, lon, moduleId, obsDate,
        happened ? "occurred" : "none",
        happened ? severity : null,
        note.trim(),
      );
      setMsg(
        happened
          ? "Đã ghi nhận. Nếu phần mềm đã báo trước thì đây là một lần đúng; nếu không thì đây là một lần bỏ sót — cả hai đều làm mô hình chuẩn hơn."
          : "Đã ghi nhận 'không xảy ra'. Loại quan sát này quan trọng ngang với loại kia: không có nó thì không đo được tỉ lệ báo động giả.",
      );
      setNote("");
      setObsOpen(false);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!user) {
    return (
      <div className="pan">
        <div className="pan-head">🔁 Cho phần mềm biết thực tế</div>
        <p className="pan-sub">
          Đăng nhập để báo lại chuyện đã thực sự xảy ra trên thửa. Đây là thứ
          duy nhất làm cảnh báo chuẩn dần lên cho chính vùng của bạn.
        </p>
      </div>
    );
  }

  return (
    <div className="pan">
      <div className="pan-head">🔁 Cho phần mềm biết thực tế</div>
      <p className="pan-sub">
        Cảnh báo chỉ chuẩn lên được khi biết nó đã đúng hay sai. Hai câu hỏi thôi.
      </p>

      {msg && <p className="fb-ok">✓ {msg}</p>}
      {err && <p className="pan-err">⚠️ {err}</p>}

      <button className="pan-go" disabled={busy} onClick={markDone}>
        ✅ Tôi đã làm theo khuyến nghị này
      </button>

      {!obsOpen ? (
        <button className="pan-ghost" onClick={() => setObsOpen(true)}>
          📋 Ghi nhận chuyện đã xảy ra ({moduleName})
        </button>
      ) : (
        <div className="fb-obs">
          <label>
            Ngày quan sát
            <input
              type="date"
              value={obsDate}
              max={today()}
              onChange={(e) => setObsDate(e.target.value)}
            />
          </label>
          <label>
            Mức độ (nếu có xảy ra)
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {SEVERITY.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <textarea
            rows={2}
            maxLength={2000}
            placeholder="Mô tả ngắn (không bắt buộc)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="fb-obs-actions">
            <button className="bad" disabled={busy} onClick={() => sendObs(true)}>
              Có xảy ra
            </button>
            <button className="good" disabled={busy} onClick={() => sendObs(false)}>
              Không xảy ra
            </button>
            <button className="ghost" onClick={() => setObsOpen(false)}>
              Huỷ
            </button>
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <div className="fb-pending">
          <div className="fb-pending-h">
            Đang chờ bạn cho biết kết quả ({pending.length})
          </div>
          {pending.slice(0, 3).map((a) => (
            <div key={a.id} className="fb-pend">
              <p>
                <b>{a.module_id}</b> · {a.acted_on}
              </p>
              <p className="fb-rec">{a.recommendation}</p>
              <div className="fb-outcomes">
                {OUTCOMES.map((o) => (
                  <button key={o.id} disabled={busy} onClick={() => outcome(a.id, o.id)}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="pan-caveat">
        Quan sát thô KHÔNG rời khỏi tài khoản của bạn. Thứ được chia sẻ ra chỉ
        là một con số hiệu chỉnh cho mỗi vùng ~0,5° và chỉ khi vùng đó đã đủ 3
        quan sát, nên không truy ngược được về thửa hay người nào.
      </p>
    </div>
  );
}
