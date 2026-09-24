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
import { useLang } from "@/lib/i18n";

const TOPICS: { id: string; vi: string; en: string }[] = [
  { id: "mặn", vi: "mặn", en: "salinity" },
  { id: "hạn", vi: "hạn", en: "drought" },
  { id: "lũ", vi: "lũ", en: "flood" },
  { id: "sâu bệnh", vi: "sâu bệnh", en: "pests" },
  { id: "giống", vi: "giống", en: "seed variety" },
  { id: "thị trường", vi: "thị trường", en: "market" },
  { id: "khác", vi: "khác", en: "other" },
];

export default function Knowledge({
  lat,
  lon,
  user,
}: {
  lat: number;
  lon: number;
  user: AuthUser | null;
}) {
  const { t } = useLang();
  const [data, setData] = useState<KnowledgeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [topic, setTopic] = useState(TOPICS[0].id);

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
      <div className="pan-head">🤝 {t("Kinh nghiệm từ vùng giống thửa của bạn", "Experience from areas similar to your plot")}</div>

      {busy && !data && <p className="pan-sub">{t("Đang tìm…", "Searching…")}</p>}
      {err && <p className="pan-err">⚠️ {err}</p>}

      {data && data.notes.length === 0 && (
        <p className="pan-sub">
          {data.message ?? t("Chưa có ai chia sẻ kinh nghiệm cho vùng này.",
                             "No one has shared experience for this area yet.")}
        </p>
      )}

      {data && data.notes.length > 0 && (
        <>
          {data.matched_by && (
            <p className="kn-match">{t(`Ghép theo ${data.matched_by}`, `Matched by ${data.matched_by}`)}</p>
          )}
          {data.notes.map((n) => (
            <div key={n.id} className="kn-note">
              <div className="kn-top">
                <b>{n.title}</b>
                {n.similarity_pct != null && (
                  <span className="kn-sim">{t(`${n.similarity_pct}% giống`, `${n.similarity_pct}% similar`)}</span>
                )}
              </div>
              <p className="kn-body">{n.body}</p>
              <div className="kn-foot">
                <span>
                  {n.author_name} · {n.topic}
                </span>
                <button onClick={() => helpful(n.id)} disabled={!user}>
                  👍 {t(`hữu ích (${n.helpful_count})`, `helpful (${n.helpful_count})`)}
                </button>
              </div>
            </div>
          ))}
          {data.why && <p className="pan-why">{data.why}</p>}
        </>
      )}

      {!user && (
        <p className="pan-note">{t("Đăng nhập để chia sẻ kinh nghiệm của bạn.", "Log in to share your experience.")}</p>
      )}

      {user && !writing && (
        <button className="pan-ghost" onClick={() => setWriting(true)}>
          + {t("Chia sẻ kinh nghiệm của tôi", "Share my experience")}
        </button>
      )}

      {user && writing && (
        <div className="kn-form">
          <select value={topic} onChange={(e) => setTopic(e.target.value)}>
            {TOPICS.map((tp) => (
              <option key={tp.id} value={tp.id}>
                {t(tp.vi, tp.en)}
              </option>
            ))}
          </select>
          <input
            placeholder={t("Tóm tắt một câu — vd. Đắp bờ bao trước Tết giữ được vụ",
                           "One-sentence summary — e.g. Building up the dike before Tết saved the crop")}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
          <textarea
            placeholder={t("Bạn đã làm gì, vào lúc nào, kết quả ra sao? Càng cụ thể càng dùng được cho người cùng vùng.",
                           "What did you do, when, and what was the result? The more specific, the more useful for people in the same area.")}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={5000}
            rows={4}
          />
          <div className="kn-actions">
            <button onClick={submit} disabled={!canSubmit}>
              {t("Chia sẻ", "Share")}
            </button>
            <button className="ghost" onClick={() => setWriting(false)}>
              {t("Huỷ", "Cancel")}
            </button>
          </div>
        </div>
      )}

      {data?.note && <p className="pan-caveat">{data.note}</p>}
    </div>
  );
}
