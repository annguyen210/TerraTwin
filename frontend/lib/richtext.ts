// Chữ đậm trong câu trả lời của trợ lý (kiểm 21/11/2026): LLM hay trả markdown "**5 đợt**", mà khung trả lời in nguyên văn
// nên dấu ** lộ ra màn hình. Tách theo regex thành các đoạn thường / đậm để vẽ bằng phần tử React — KHÔNG dùng
// dangerouslySetInnerHTML (câu trả lời là chữ từ mô hình bên ngoài). Dấu ** lẻ, không thành cặp, thì bỏ.
export type Part = { text: string; bold: boolean };

export function boldParts(s: string): Part[] {
  const out: Part[] = [];
  const re = /\*\*([^*\n]+?)\*\*|__([^_\n]+?)__/g;
  let last = 0;
  for (let m = re.exec(s); m; m = re.exec(s)) {
    if (m.index > last) out.push({ text: s.slice(last, m.index), bold: false });
    out.push({ text: m[1] ?? m[2], bold: true });
    last = re.lastIndex;
  }
  if (last < s.length) out.push({ text: s.slice(last), bold: false });
  return out.map((p) => (p.bold ? p : { ...p, text: p.text.replace(/\*\*|__/g, "").replace(/^#{1,6}\s+/gm, "") }));
}
