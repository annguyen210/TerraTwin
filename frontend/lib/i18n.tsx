"use client";

/**
 * i18n tối giản — KHÔNG thư viện, KHÔNG từ điển trung tâm.
 *
 * Cách dùng: const { t } = useLang();  {t("mũi nhọn", "modules")}
 * Bản dịch nằm NGAY tại chỗ dùng — dễ đọc, dễ giữ đồng bộ, không lạc khoá.
 *
 * PHẠM VI CÓ CHỦ Ý: chỉ dịch phần GIAO DIỆN/marketing mà người xem quốc tế đọc.
 * Dữ liệu per-thửa (tên mũi nhọn, khuyến nghị) đến từ backend bằng tiếng Việt —
 * đó là nội dung lĩnh vực cho nông dân Việt, giữ nguyên là đúng, không dịch máy.
 */

import {
  createContext, useContext, useEffect, useState, type ReactNode,
} from "react";

type Lang = "vi" | "en";
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (vi: string, en: string) => string };

const LangCtx = createContext<Ctx>({ lang: "vi", setLang: () => {}, t: (vi) => vi });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("vi");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("terratwin_lang");
      if (saved === "en" || saved === "vi") {
        setLangState(saved);
        document.documentElement.lang = saved;
      }
    } catch {
      /* ignore */
    }
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("terratwin_lang", l);
      document.documentElement.lang = l;
    } catch {
      /* ignore */
    }
  };

  const t = (vi: string, en: string) => (lang === "en" ? en : vi);

  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export const useLang = () => useContext(LangCtx);

/** Nút chuyển VI/EN — dùng ở thanh trên. */
export function LangToggle() {
  const { lang, setLang } = useLang();
  return (
    <div className="lang-toggle" role="group" aria-label="Ngôn ngữ / Language">
      <button
        className={lang === "vi" ? "on" : ""}
        onClick={() => setLang("vi")}
        aria-pressed={lang === "vi"}
      >
        VI
      </button>
      <button
        className={lang === "en" ? "on" : ""}
        onClick={() => setLang("en")}
        aria-pressed={lang === "en"}
      >
        EN
      </button>
    </div>
  );
}
