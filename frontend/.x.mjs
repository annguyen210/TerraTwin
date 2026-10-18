export default async function (page) {
  await page.goto("https://github.com/annguyen210/TerraTwin/actions", { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForTimeout(4000);
  const rows = await page.evaluate(() => [...document.querySelectorAll("a[href*='/actions/runs/']")]
    .map((a) => { const row = a.closest("div[class*='Box-row'], li, [data-testid*='row']") || a.parentElement;
                  const st = row && row.querySelector("svg[aria-label]"); return (st ? st.getAttribute("aria-label") : "?") + " | " + (row ? row.innerText : a.innerText).replace(/\s+/g, " ").slice(0, 150); })
    .filter((v, i, s) => s.indexOf(v) === i).slice(0, 10));
  for (const r of rows) console.log("QA>", r);
}
