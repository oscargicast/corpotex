// Backup video of the demo, as a guide for a manual recording (docs/demo/guion-visual.md).
// Runs the visual script headless against the real API with Playwright video
// recording; compose.sh stitches the segments with ffmpeg. No audio.
//
//   node record.mjs                     -> segments in ./out/ (one .webm per window)
//   ./compose.sh ~/Desktop/corpotex-demo-respaldo.mp4
//
// Needs Google Chrome, ffmpeg, and playwright-core (PLAYWRIGHT_CORE=<path to the
// package>, or installed; once: node <playwright-core>/cli.js install ffmpeg).
// Env: BASE (default http://127.0.0.1:3000), SEED_USERS_PASSWORD (read from the
// repo .env when missing), SEGMENTS=01,02 to run a subset, DRY=1 to skip every
// click that mutates data or spends an agent turn.
//
// It mutates the demo data (new order, approvals, the cancellation of PT-0038,
// a progress report and a payment): run `seed_demo` afterwards. Agent turns are
// real, so run it only when nobody else is using the stack.
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";

const { chromium } = await import(process.env.PLAYWRIGHT_CORE ?? "playwright-core");
const REPO = new URL("../../../", import.meta.url).pathname;

const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const OUT = new URL("./out/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const password =
  process.env.SEED_USERS_PASSWORD ??
  readFileSync(`${REPO}.env`, "utf8")
    .split("\n")
    .find((l) => l.startsWith("SEED_USERS_PASSWORD="))
    ?.split("=")
    .slice(1)
    .join("=")
    .trim()
    .replace(/^["']|["']$/g, "");
if (!password) throw new Error("SEED_USERS_PASSWORD not found");

const log = [];
const state = {};
const t0 = Date.now();
function mark(label) {
  const t = ((Date.now() - t0) / 1000).toFixed(1);
  log.push(`${t}s ${label}`);
  console.log(`${t}s ${label}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page, username) {
  const res = await page.request.post(`${BASE}/api/auth/login/`, { data: { username, password } });
  if (!res.ok()) throw new Error(`login ${username}: ${res.status()}`);
  const { token, user } = await res.json();
  if (username === "gerente") state.token = token;
  await page.goto(`${BASE}/login`);
  await page.evaluate(
    ([t, u]) => {
      sessionStorage.setItem("corpotex.token", t);
      sessionStorage.setItem("corpotex.user", JSON.stringify(u));
    },
    [token, user],
  );
  return token;
}

// SEGMENTS=01,02 runs only those (dry runs of the read-only parts).
const ONLY = process.env.SEGMENTS?.split(",").filter(Boolean);
// DRY=1 records everything but skips the clicks that mutate data or spend an
// agent turn (submit order, confirm, approve, send in the simulator, Sí, report, pay).
const DRY = process.env.DRY === "1";

// Each segment is one or two contexts recorded at the same time.
async function segment(browser, name, viewports, run) {
  if (ONLY && !ONLY.some((p) => name.startsWith(p))) return;
  const contexts = [];
  for (const [i, viewport] of viewports.entries()) {
    const dir = `${OUT}${name}-${i}/`;
    mkdirSync(dir, { recursive: true });
    contexts.push(await browser.newContext({ viewport, recordVideo: { dir, size: viewport }, deviceScaleFactor: 1 }));
  }
  const pages = await Promise.all(contexts.map((c) => c.newPage()));
  mark(`segment ${name}: start`);
  try {
    await run(pages);
  } catch (err) {
    mark(`segment ${name}: ERROR ${err.message}`);
    await Promise.all(pages.map((p, i) => p.screenshot({ path: `${OUT}${name}-${i}-error.png` }).catch(() => null)));
  }
  await sleep(1500);
  await Promise.all(contexts.map((c) => c.close()));
  mark(`segment ${name}: end`);
}

const settle = async (page, ms = 2500) => {
  await page.waitForLoadState("networkidle").catch(() => null);
  await sleep(ms);
};

async function waitText(page, text, timeout = 30_000) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ timeout });
    return true;
  } catch {
    mark(`timeout waiting for "${text}"`);
    return false;
  }
}

// The "Aprobar" of the card that holds `anchor` (a button or heading locator):
// the Monitor lists several decisions and .first() could hit another one.
function approveNear(anchor) {
  return anchor.locator("xpath=ancestor::*[.//button[normalize-space()='Aprobar']][1]").getByRole("button", { name: "Aprobar" }).first();
}

async function waitGone(locator, timeout) {
  try {
    await locator.waitFor({ state: "hidden", timeout });
    return true;
  } catch {
    return false;
  }
}

// The supplier that reports progress and gets paid at the end: a purchase order
// of the redistribution if there is one (PT-0038 is cancelled by then), else PT-0038.
async function pickReportPo(page) {
  const fallback = { code: "PT-0038", token: "11111111-1111-4111-8111-000000000038" };
  try {
    const list = await (await page.request.get(`${BASE}/api/purchase-orders/`, { headers: { Authorization: `Token ${state.token}` } })).json();
    const open = list.filter(
      (po) => po.code !== "PT-0038" && (po.orders ?? []).some((o) => o.code === "CP-2026-0142") && !/cancel|declined|delivered|closed/.test(po.status),
    );
    for (const po of open) {
      const detail = await (await page.request.get(`${BASE}/api/purchase-orders/${po.id}/`, { headers: { Authorization: `Token ${state.token}` } })).json();
      if (detail.report_token) return { code: po.code, token: detail.report_token, id: po.id };
    }
  } catch (err) {
    mark(`pickReportPo: ${err.message}`);
  }
  return fallback;
}

async function main() {
  const browser = await chromium.launch({ channel: "chrome", headless: true }).catch(() => chromium.launch({ headless: true }));
  const L = { width: 960, height: 1080 };
  const W = { width: 1920, height: 1080 };
  const M = { width: 390, height: 844 };

  // 1 and 2: Monitor and Configuración (single wide window).
  await segment(browser, "01-monitor", [W], async ([g]) => {
    await login(g, "gerente");
    await g.goto(`${BASE}/`);
    await settle(g, 6000);
    await g.goto(`${BASE}/settings`);
    await settle(g, 3000);
    await g.goto(`${BASE}/settings/style`);
    await settle(g, 6000);
  });

  // 3 to 5: Comercial registers, Producción confirms, Gerente approves (two windows).
  await segment(browser, "02-orden", [L, L], async ([g, c]) => {
    await login(g, "gerente");
    await login(c, "comercial");
    await g.goto(`${BASE}/`);
    await c.goto(`${BASE}/orders`);
    await settle(c, 3000);
    await c.getByRole("button", { name: "Simular orden de Comercial" }).click();
    await sleep(1500);
    if (DRY) {
      await sleep(3000);
      await c.keyboard.press("Escape");
      state.orderUrl = "/orders/" + (process.env.ORDER_ID ?? "1");
    } else {
      await c.getByRole("button", { name: /Caja Piura/ }).click();
      await c.waitForURL(/\/orders\/\d+/, { timeout: 30_000 });
      state.orderUrl = new URL(c.url()).pathname;
      mark(`orden nueva: ${state.orderUrl}`);
    }
    await settle(c, 5000);
    await g.goto(`${BASE}${state.orderUrl}`);
    await settle(g, 4000);
    const confirm = g.getByRole("button", { name: "Confirmar desglose" });
    if (!DRY && (await confirm.isVisible().catch(() => false))) {
      await confirm.click();
      await sleep(4000);
    }
    await g.goto(`${BASE}/`);
    await settle(g, 4000);
    const change = g.getByRole("button", { name: "Cambiar proveedor" }).first();
    if (await change.isVisible().catch(() => false)) {
      await change.click();
      await sleep(5000);
      await g.getByRole("button", { name: "Cerrar" }).click();
      await sleep(1000);
      const approve = approveNear(change);
      if (!DRY && (await approve.isVisible().catch(() => false))) {
        await approve.click();
        await sleep(4000);
      }
    } else {
      mark("no assignment decision with 'Cambiar proveedor' on the Monitor");
    }
    await c.goto(`${BASE}/`);
    await settle(c, 3000);
  });

  // 6 and 7: the supplier chat and the cancellation through the simulator (presentation mode).
  await segment(browser, "03-simulador", [W], async ([g]) => {
    await login(g, "gerente");
    await g.goto(`${BASE}/simulator?present=1`);
    await settle(g, 3000);
    // Confecciones del Norte, the workshop of PT-0038: the simulated contact, never the real WhatsApp one.
    const contact = g.locator("nav[aria-label='Contactos'] button").filter({ hasText: "Confecciones del Norte" }).filter({ hasNotText: "WhatsApp real" }).first();
    await contact.click();
    await sleep(2500);
    const agentBubbles = g.getByText("Agente", { exact: true });
    const bubblesBefore = await agentBubbles.count();
    const box = g.getByRole("textbox", { name: /Mensaje de/ });
    await box.fill("Jefe, no voy a poder terminar. Se me malogró la máquina.");
    await sleep(1500);
    if (DRY) {
      await box.fill("");
      await sleep(2000);
      return;
    }
    await box.press("Enter");
    mark("cancelación enviada");
    await waitText(g, "Escribiendo", 15_000);
    const deadline = Date.now() + 90_000;
    while (Date.now() < deadline && (await agentBubbles.count()) <= bubblesBefore) await sleep(1000);
    mark(`agente respondió: ${(await agentBubbles.count()) > bubblesBefore}`);
    await sleep(4000);
    await waitText(g, "Nuevo mensaje para", 40_000);
    await sleep(6000);
  });

  // 8 and 9: redistribution, route and notices per role (two windows).
  await segment(browser, "04-redistribucion", [L, L], async ([g, c]) => {
    await login(g, "gerente");
    await login(c, "comercial");
    await g.goto(`${BASE}/`);
    await c.goto(`${BASE}/`);
    await settle(g, 5000);
    const route = g.getByRole("link", { name: "Ver la ruta nueva" }).first();
    if (await route.isVisible().catch(() => false)) {
      await route.click();
      await g.waitForURL(/\/routes/, { timeout: 15_000 });
      await settle(g, 7000);
      await g.goto(`${BASE}/`);
      await settle(g, 3000);
    }
    await g.locator("header button[aria-expanded]").click();
    await c.locator("header button[aria-expanded]").click();
    await sleep(5000);
    const yes = g.getByRole("button", { name: "Sí", exact: true });
    // The redistribution lives in the decision card that links to the new route.
    const card = g.getByRole("link", { name: "Ver la ruta nueva" }).first();
    if (DRY) {
      // nothing to approve in a dry run
    } else {
      if (await yes.isVisible().catch(() => false)) {
        await yes.click();
        mark("Sí en el asistente");
        await waitGone(card, 60_000);
      }
      const approve = approveNear(card);
      if ((await card.isVisible().catch(() => false)) && (await approve.isVisible().catch(() => false))) {
        await approve.click();
        mark("Aprobar en la tarjeta");
        await waitGone(card, 20_000);
      }
    }
    await sleep(6000);
    state.report = await pickReportPo(g);
    mark(`reporte sobre ${state.report.code}`);
  });

  // 10: the workshop reports from the phone, then the photo and the payment (Gerente).
  await segment(browser, "05-celular", [M], async ([m]) => {
    const report = state.report ?? { code: "PT-0038", token: "11111111-1111-4111-8111-000000000038" };
    await m.goto(`${BASE}/report/${report.token}`);
    await settle(m, 3000);
    const units = m.getByRole("spinbutton");
    const total = Number((await m.getByText(/prendas/).first().innerText()).match(/(\d+) prendas/)?.[1] ?? 1000);
    await units.fill(String(Math.min(500, total)));
    await sleep(800);
    await m.locator("input[type=file]").setInputFiles(`${REPO}frontend/public/demo-photos/UNI-POD-01.jpg`).catch((e) => mark(`foto: ${e.message}`));
    await sleep(1000);
    if (DRY) return;
    await m.getByRole("button", { name: "Enviar avance" }).click();
    await waitText(m, "Avance registrado", 20_000);
    await sleep(3000);
  });
  await segment(browser, "06-pago", [W], async ([g]) => {
    await login(g, "gerente");
    await g.goto(`${BASE}/purchase-orders/${state.report?.code ?? "PT-0038"}`);
    await settle(g, 4000);
    const zoom = g.locator('[role=button][aria-label^="Ver en grande"]').first();
    if (await zoom.isVisible().catch(() => false)) {
      await zoom.click();
      await sleep(3000);
      await g.keyboard.press("Escape");
      await sleep(1000);
    }
    const pay = g.getByRole("button", { name: "Marcar pagado" }).first();
    if (!DRY && (await pay.isVisible().catch(() => false))) {
      await pay.click();
      await sleep(1500);
      await g.getByRole("button", { name: "Confirmar pago" }).click();
      await sleep(4000);
    }
  });

  await browser.close();
  writeFileSync(`${OUT}log.txt`, log.join("\n") + "\n");
  mark("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
