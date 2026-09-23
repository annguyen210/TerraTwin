// Kiểm tra lỗi dev-mode CSP đã báo trước: `next dev` cần 'unsafe-eval' cho
// Fast Refresh (webpack eval-source-map), production thì không — nới nhầm
// bên production là lỗ hổng, thiếu bên dev là Fast Refresh gãy im lặng.
import assert from "node:assert/strict";

async function cspFor(nodeEnv) {
  const prev = process.env.NODE_ENV;
  process.env.NODE_ENV = nodeEnv;
  try {
    const mod = await import(`../next.config.mjs?t=${Date.now()}`);
    const headerGroups = await mod.default.headers();
    const main = headerGroups.find((g) => g.source === "/:path*");
    return main.headers.find((h) => h.key === "Content-Security-Policy").value;
  } finally {
    process.env.NODE_ENV = prev;
  }
}

const devCsp = await cspFor("development");
assert.match(devCsp, /script-src[^;]*'unsafe-eval'/,
  "dev CSP phải cho 'unsafe-eval' — thiếu thì Fast Refresh gãy");

const prodCsp = await cspFor("production");
assert.doesNotMatch(prodCsp, /'unsafe-eval'/,
  "production CSP KHÔNG được có 'unsafe-eval' — đây là lỗ hổng nếu lọt vào prod");

console.log("OK — CSP: dev có unsafe-eval, production không.");
