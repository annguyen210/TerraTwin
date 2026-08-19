"use client";

/**
 * U02 Chợ tri thức — kinh nghiệm từ vùng có CÙNG BỘ GEN ĐẤT, không phải cùng tỉnh.
 *
 * Một hộ cách 200 km nhưng cùng cao độ, chế độ mưa và mức mặn cho kinh nghiệm
 * dùng được ngay; một hộ cách 20 km nhưng ở trên đồi thì không. Ghép theo bộ
 * gen là điểm khác biệt của chợ này so với một diễn đàn thông thường.
 */

import { useCallback, useEffect, useState } from "react";
import {
  findKnowledge,
  markHelpful,
  shareKnowledge,
  type AuthUser,
  type KnowledgeResult,
} from "@/lib/api";

const TOPICS = ["mặn", "hạn", "lũ", "sâu bệnh", "giống", "thị trường", "khác"];

export default function Knowledge({
  lat,
  lon,
  user,
}: {
  lat: number;
  lon: number;
  user: AuthUser | null;
}) {
  const [data, setData] = useState<KnowledgeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [topic, setTopic] = useState(TOPICS[0]);

  const load = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      setData(await findKnowledge(lat, lon));
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }, [lat, lon]);

  useEffect(() => {
    load();
  }, [load]);

  async function submit() {
    setErr(null);
    try {
      await shareKnowledge(lat, lon, title.trim(), body.trim(), topic);
      setTitle("");
      setBody("");
      setWriting(false);
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function helpful(id: number) {
    try {
      await markHelpful(id);
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const canSubmit = title.trim().length >= 3 && body.trim().length >= 10;

  return (
    <div className="pan">
      <div className="pan-head">🤝 Kinh nghiệm từ vùng giống thửa của bạn</div>

      {busy && !data && <p className="pan-sub">Đang tìm…</p>}
      {err && <p className="pan-err">⚠️ {err}</p>}

      {data && data.notes.length === 0 && (
        <p className="pan-sub">
          {data.message ?? "Chưa có ai chia sẻ kinh nghiệm cho vùng này."}
        </p>
      )}

      {data && data.notes.length > 0 && (
        <>
          {data.matched_by && (
            <p className="kn-match">Ghép theo {data.matched_by}</p>
          )}
          {data.notes.map((n) => (
            <div key={n.id} className="kn-note">
              <div className="kn-top">
                <b>{n.title}</b>
                {n.similarity_pct != null && (
                  <span className="kn-sim">{n.similarity_pct}% giống</span>
                )}
              </div>
              <p className="kn-body">{n.body}</p>
              <div className="kn-foot">
                <span>
                  {n.author_name} · {n.topic}
                </span>
                <button onClick={() => helpful(n.id)} disabled={!user}>
                  👍 hữu ích ({n.helpful_count})
                </button>
              </div>
            </div>
          ))}
          {data.why && <p className="pan-why">{data.why}</p>}
        </>
      )}

      {!user && (
        <p className="pan-note">Đăng nhập để chia sẻ kinh nghiệm của bạn.</p>
      )}

      {user && !writing && (
        <button className="pan-ghost" onClick={() => setWriting(true)}>
          + Chia sẻ kinh nghiệm của tôi
        </button>
      )}

      {user && writing && (
        <div className="kn-form">
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            {TOPICS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            placeholder="Tóm tắt một câu — vd. Đắp bờ bao trước Tết giữ được vụ"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
          <textarea
            placeholder="Bạn đã làm gì, vào lúc nào, kết quả ra sao? Càng cụ thể càng dùng được cho người cùng vùng."
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={5000}
            rows={4}
          />
          <div className="kn-actions">
            <button onClick={submit} disabled={!canSubmit}>
              Chia sẻ
            </button>
            <button className="ghost" onClick={() => setWriting(false)}>
              Huỷ
            </button>
          </div>
        </div>
      )}

      {data?.note && <p className="pan-caveat">{data.note}</p>}
    </div>
  );
}
