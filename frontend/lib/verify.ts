/**
 * KIỂM CHỨNG NGAY TRONG TRÌNH DUYỆT — không gọi máy chủ TerraTwin.
 *
 * Người nhận hồ sơ (nhà nhập khẩu EU, ngân hàng) không cần tin máy chủ: trình duyệt tự
 *   1. băm lại `facts_canonical` (đúng chuỗi đã băm lúc phát hành — không dựng lại JSON,
 *      vì JavaScript viết số khác Python: 4 / 4.0) và so với facts_hash,
 *   2. dựng lại entry_message từ các trường và băm → entry_hash,
 *   3. kiểm chữ ký Ed25519 trên entry_hash bằng WebCrypto,
 *   4. kiểm bằng chứng Merkle (RFC 9162 §2.1.3.2) cho chứng thư lô hàng / sổ minh bạch.
 */

const enc = new TextEncoder();

/** Bản ArrayBuffer riêng — WebCrypto (TS 5.7+) không nhận Uint8Array trên SharedArrayBuffer. */
function ab(u: Uint8Array): ArrayBuffer {
  return u.buffer.slice(u.byteOffset, u.byteOffset + u.byteLength) as ArrayBuffer;
}

function toHex(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function fromHex(h: string): Uint8Array {
  const out = new Uint8Array(h.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(h.slice(2 * i, 2 * i + 2), 16);
  return out;
}

function fromB64(b: string): Uint8Array {
  const s = atob(b);
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}

export async function sha256Hex(data: string | Uint8Array): Promise<string> {
  const bytes = typeof data === "string" ? enc.encode(data) : data;
  return toHex(await crypto.subtle.digest("SHA-256", ab(bytes)));
}

async function sha256(bytes: Uint8Array): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", ab(bytes)));
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

/** true/false — hoặc null khi trình duyệt chưa hỗ trợ Ed25519 trong WebCrypto. */
export async function verifyEd25519(pubB64: string, sigB64: string, message: string): Promise<boolean | null> {
  try {
    const key = await crypto.subtle.importKey("raw", ab(fromB64(pubB64)), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, ab(fromB64(sigB64)), ab(enc.encode(message)));
  } catch (e) {
    const name = (e as DOMException)?.name;
    if (name === "NotSupportedError" || name === "SyntaxError" || name === "TypeError") return null;
    return false;
  }
}

export async function leafHash(data: Uint8Array): Promise<Uint8Array> {
  return sha256(concat(new Uint8Array([0]), data));
}

async function nodeHash(l: Uint8Array, r: Uint8Array): Promise<Uint8Array> {
  return sha256(concat(new Uint8Array([1]), l, r));
}

function eq(a: Uint8Array, b: Uint8Array) {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** RFC 9162 §2.1.3.2 — đường kiểm toán từ lá tới gốc. */
export async function verifyInclusion(leafHex: string, index: number, size: number, proofHex: string[], rootHex: string): Promise<boolean> {
  if (index < 0 || index >= size) return false;
  let fn = index, sn = size - 1;
  let r = fromHex(leafHex);
  for (const ph of proofHex) {
    const p = fromHex(ph);
    if (sn === 0) return false;
    if (fn & 1 || fn === sn) {
      r = await nodeHash(p, r);
      if (!(fn & 1)) {
        do { fn >>= 1; sn >>= 1; } while (!(fn & 1) && fn !== 0);
      }
    } else {
      r = await nodeHash(r, p);
    }
    fn >>= 1; sn >>= 1;
  }
  return sn === 0 && eq(r, fromHex(rootHex));
}

export type CheckLine = { id: string; ok: boolean | null; label: string };

export type DossierFile = {
  id: string; seq: number; issued_at: string; facts: Record<string, unknown>; facts_canonical?: string;
  proof: { schema: string; facts_hash: string; prev_hash: string; entry_hash: string; algorithm: string;
           key_id: string; signature: string; public_key_b64?: string | null; entry_message?: string };
};

/** Kiểm một tệp hồ sơ hoàn toàn offline. */
export async function verifyDossierOffline(doc: DossierFile, t: (vi: string, en: string) => string): Promise<CheckLine[]> {
  const out: CheckLine[] = [];
  const p = doc.proof;
  if (!doc.facts_canonical) {
    out.push({ id: "content", ok: null, label: t("Tệp không có facts_canonical (tải lại từ TerraTwin bản mới) — chưa kiểm được nội dung offline.",
      "File has no facts_canonical (re-download from TerraTwin) — content can't be checked offline.") });
  } else {
    const h = await sha256Hex(doc.facts_canonical);
    let same = false;
    try { same = JSON.stringify(JSON.parse(doc.facts_canonical)) === JSON.stringify(doc.facts); } catch { same = false; }
    out.push({ id: "content", ok: h === p.facts_hash && same, label: h === p.facts_hash && same
      ? t("Nội dung khớp mã băm SHA-256 lúc phát hành", "Content matches its issuance SHA-256 hash")
      : t("Nội dung ĐÃ BỊ SỬA so với lúc phát hành", "Content was ALTERED since issuance") });
  }
  const msg = `${p.schema}|${doc.seq}|${doc.id}|${doc.issued_at}|${p.facts_hash}|${p.prev_hash}`;
  const eh = await sha256Hex(msg);
  out.push({ id: "entry", ok: eh === p.entry_hash, label: eh === p.entry_hash
    ? t("Mục sổ đăng ký (số thứ tự, mã, thời điểm, mắt xích) toàn vẹn", "Registry entry (seq, ID, time, chain link) intact")
    : t("Mục sổ đăng ký bị sửa", "Registry entry altered") });
  if (!p.public_key_b64) {
    out.push({ id: "signature", ok: null, label: t("Tệp không kèm khoá công khai — chưa kiểm chữ ký offline.", "No public key in the file — signature not checked offline.") });
  } else {
    const ok = await verifyEd25519(p.public_key_b64, p.signature, p.entry_hash);
    out.push({ id: "signature", ok, label: ok === null
      ? t("Trình duyệt này chưa hỗ trợ Ed25519 (cần Chrome 137+, Firefox 129+, Safari 17+).", "This browser lacks Ed25519 support (needs Chrome 137+, Firefox 129+, Safari 17+).")
      : ok ? t(`Chữ ký Ed25519 hợp lệ (khoá ${p.key_id})`, `Valid Ed25519 signature (key ${p.key_id})`)
        : t("Chữ ký KHÔNG hợp lệ", "Signature INVALID") });
  }
  return out;
}
