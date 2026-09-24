"use client";

import { useEffect, useRef, useState } from "react";
import { runAsk, type AskResult } from "@/lib/api";
import { useLang } from "@/lib/i18n";

/** C09 Field Mode — hỏi bằng GIỌNG NÓI, dùng được ngay ngoài đồng.
 *
 *  Nông dân đứng giữa ruộng, tay bẩn, nắng chói: gõ phím là rào cản thật.
 *  Dùng Web Speech API có sẵn trong trình duyệt — miễn phí, không cần key,
 *  không gửi âm thanh về máy chủ của chúng tôi.
 *
 *  Trình duyệt không hỗ trợ (Firefox, một số WebView) thì vẫn gõ tay được —
 *  tính năng này là lối tắt, không phải điều kiện bắt buộc.
 */

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
};

function getRecognition(): SpeechRecognitionLike | null {
  if (typeof window === "undefined") return null;
  const Ctor =
    (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
  if (!Ctor) return null;
  const r: SpeechRecognitionLike = new Ctor();
  r.lang = "vi-VN";
  r.continuous = false;
  r.interimResults = true;
  return r;
}

const EXAMPLES = [
  "nếu mưa gấp đôi thì ruộng tôi có ngập không",
  "mưa giảm 60% thì hạn thế nào",
  "nóng thêm 3 độ có cháy rừng không",
];

export default function FieldMode({
  moduleId,
  lat,
  lon,
}: {
  moduleId: string;
  lat: number;
  lon: number;
}) {
  const { t } = useLang();
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [text, setText] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    setSupported(getRecognition() !== null);
    return () => recRef.current?.stop();
  }, []);

  function toggleMic() {
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const r = getRecognition();
    if (!r) return;
    recRef.current = r;
    setErr(null);
    setResult(null);

    r.onresult = (e: any) => {
      let s = "";
      for (let i = 0; i < e.results.length; i++) s += e.results[i][0].transcript;
      setText(s);
      // Kết quả cuối cùng → hỏi luôn, người dùng không phải bấm thêm.
      if (e.results[e.results.length - 1].isFinal) submit(s);
    };
    r.onerror = (e: any) => {
      setErr(
        e?.error === "not-allowed"
          ? t("Trình duyệt chưa được cấp quyền micro.", "The browser hasn't been granted microphone access.")
          : t("Không nghe được — thử lại hoặc gõ tay.", "Couldn't hear you — try again or type instead."),
      );
      setListening(false);
    };
    r.onend = () => setListening(false);

    r.start();
    setListening(true);
  }

  async function submit(q: string) {
    const question = q.trim();
    if (!question) return;
    setBusy(true);
    setErr(null);
    try {
      setResult(await runAsk(question, lat, lon, moduleId));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="field">
      <div className="fm-head">🎤 {t("Chế độ ngoài đồng — hỏi bằng lời", "Field mode — ask out loud")}</div>

      <div className="fm-row">
        <button
          className={`fm-mic ${listening ? "on" : ""}`}
          onClick={toggleMic}
          disabled={!supported || busy}
          title={supported ? t("Bấm rồi nói", "Tap and speak") : t("Trình duyệt không hỗ trợ giọng nói", "This browser doesn't support voice input")}
        >
          {listening ? "⏹" : "🎤"}
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit(text)}
          placeholder={
            listening ? t("Đang nghe…", "Listening…") : t("Nói hoặc gõ: nếu mưa gấp đôi thì sao?", "Speak or type: what if rain doubles?")
          }
        />
        <button className="fm-go" onClick={() => submit(text)} disabled={busy}>
          {busy ? "…" : t("Hỏi", "Ask")}
        </button>
      </div>

      {!supported && (
        <p className="fm-note">
          {t("Trình duyệt này không hỗ trợ nhập bằng giọng nói — bạn vẫn gõ tay được bình thường. (Chrome và Edge hỗ trợ tốt nhất.)",
             "This browser doesn't support voice input — you can still type normally. (Chrome and Edge support it best.)")}
        </p>
      )}

      {!result && !busy && (
        <div className="fm-examples">
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => { setText(e); submit(e); }}>
              {e}
            </button>
          ))}
        </div>
      )}

      {err && <p className="err">{err}</p>}

      {result && (
        <div className="fm-answer">
          {!result.understood ? (
            <p className="fm-note">{result.message}</p>
          ) : !result.available ? (
            <p className="fm-note">{result.message}</p>
          ) : (
            <>
              <p className="fm-headline">{result.headline}</p>
              <div className="fm-bars">
                <span>
                  {t("Hiện tại", "Currently")} <b>{result.baseline_peak}</b>
                </span>
                <span className="fm-arrow">→</span>
                <span
                  className={`fm-scen ${result.risk_level}`}
                >
                  {t("Kịch bản", "Scenario")} <b>{result.scenario_peak}</b>
                </span>
              </div>
              <p className="fm-method">{result.method}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
