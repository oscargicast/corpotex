// Screen recordings for the feature video (docs/demo/video-features.md).
// Runs each scene headless against the live stack with Playwright and leaves
// one mp4 per scene in public/recordings/. Mutates demo data (new order,
// approvals, a cancellation through the simulator, a simulated route): run
// `seed_demo --reset-chats` afterwards. Never touches a real WhatsApp number.
//
//   node record.mjs                 -> every scene
//   SCENES=01,05 node record.mjs    -> a subset
//   BASE=http://127.0.0.1:3000      -> stack URL (default)
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { chromium } from "playwright-core";
import QRCode from "qrcode";

const REPO = new URL("../", import.meta.url).pathname;
const BASE = process.env.BASE ?? "http://127.0.0.1:3000";
const RAW = new URL("./out/raw/", import.meta.url).pathname;
const OUT = new URL("./public/recordings/", import.meta.url).pathname;
mkdirSync(RAW, { recursive: true });
mkdirSync(OUT, { recursive: true });
const ONLY = process.env.SCENES?.split(",").filter(Boolean);

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

const PHOTO = `${REPO}backend/seed/images/products/UNI-POD-01.jpg`;
const REAL_SUPPLIER = "Confecciones del Norte"; // bound to a real WhatsApp number: never approve anything for it
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = Date.now();
const log = [];
function mark(msg) {
  const line = `${((Date.now() - t0) / 1000).toFixed(1)}s ${msg}`;
  log.push(line);
  console.log(line);
}
const state = {};

async function login(page, username) {
  const res = await page.request.post(`${BASE}/api/auth/login/`, { data: { username, password } });
  if (!res.ok()) throw new Error(`login ${username}: ${res.status()}`);
  const { token, user } = await res.json();
  state.tokens ??= {};
  state.tokens[username] = token;
  await page.goto(`${BASE}/login`);
  await page.evaluate(
    ([t, u]) => {
      sessionStorage.setItem("corpotex.token", t);
      sessionStorage.setItem("corpotex.user", JSON.stringify(u));
    },
    [token, user],
  );
}

async function api(page, path, username = "gerente") {
  const res = await page.request.get(`${BASE}${path}`, { headers: { Authorization: `Token ${state.tokens[username]}` } });
  return res.json();
}

async function waitText(page, text, timeout = 30_000) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ timeout });
    return true;
  } catch {
    mark(`timeout waiting for "${text}"`);
    return false;
  }
}

async function scrollBy(page, px, steps = 10, pause = 120) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, px / steps);
    await sleep(pause);
  }
}

// One scene = one or two contexts recorded at the same time, then stitched.
// `parts` are recorded one after another and concatenated (same size).
async function scene(browser, name, run) {
  if (ONLY && !ONLY.some((p) => name.startsWith(p))) return;
  mark(`scene ${name}: start`);
  const parts = [];
  const part = async (viewports, fn) => {
    const contexts = [];
    for (const viewport of viewports) {
      contexts.push(await browser.newContext({ viewport, deviceScaleFactor: 1, recordVideo: { dir: RAW, size: viewport }, locale: "es-PE", timezoneId: "America/Lima" }));
    }
    const pages = await Promise.all(contexts.map((c) => c.newPage()));
    const started = Date.now();
    let skip = 0;
    // Scenes call ready() once their first real page is on screen: the login
    // flash before it is cut from the recording.
    const ready = async () => {
      skip = (Date.now() - started) / 1000;
    };
    try {
      await fn(pages, ready);
    } catch (err) {
      mark(`scene ${name}: ERROR ${err.message}`);
      await Promise.all(pages.map((p, i) => p.screenshot({ path: `${RAW}${name}-${parts.length}-${i}-error.png` }).catch(() => null)));
    }
    await sleep(1200);
    const videos = await Promise.all(pages.map((p) => p.video().path()));
    await Promise.all(contexts.map((c) => c.close()));
    parts.push({ videos, viewports, skip });
  };
  await run(part);
  stitch(name, parts);
  mark(`scene ${name}: end`);
}

// ffmpeg: each part scaled to 1920x1080 (two windows side by side), then concatenated.
function stitch(name, parts) {
  const ffmpeg = "ffmpeg";
  const partFiles = parts.map((p, i) => {
    const out = `${RAW}${name}-part${i}.mp4`;
    const ss = ["-ss", p.skip.toFixed(2)];
    if (p.videos.length === 2) {
      execFileSync(ffmpeg, ["-v", "error", "-y", ...ss, "-i", p.videos[0], ...ss, "-i", p.videos[1], "-filter_complex", "[0:v]scale=960:1080:flags=lanczos[l];[1:v]scale=960:1080:flags=lanczos[r];[l][r]hstack=inputs=2,fps=30,format=yuv420p[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out]);
    } else {
      execFileSync(ffmpeg, ["-v", "error", "-y", ...ss, "-i", p.videos[0], "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out]);
    }
    return out;
  });
  const list = `${RAW}${name}-list.txt`;
  writeFileSync(list, partFiles.map((f) => `file '${f}'`).join("\n") + "\n");
  execFileSync(ffmpeg, ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", `${OUT}${name}.mp4`]);
  const seconds = execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", `${OUT}${name}.mp4`]).toString().trim();
  mark(`${name}.mp4: ${Number(seconds).toFixed(1)}s`);
}

const W = { width: 1536, height: 864 }; // scaled to 1920x1080: like Chrome at 125 %
const H = { width: 960, height: 1080 }; // two windows side by side

async function main() {
  const browser = await chromium.launch({ channel: "chrome", headless: true });

  // 1. Puesta en marcha: Claude, WhatsApp (QR) y estilo. The connected state is
  // real; the "not connected" state and the QR are mocked at the network layer.
  await scene(browser, "01-onboarding", async (part) => {
    await part([W], async ([g], ready) => {
      await login(g, "gerente");
      const qr = await QRCode.toDataURL("https://corpotex.oscargicast.com", { width: 512, margin: 1 });
      const waReal = await api(g, "/api/onboarding/whatsapp/");
      await g.route("**/api/settings/claude/status/", (route) =>
        route.fulfill({ json: { connected: false, method: null, subscription_type: null, expires_at: null, refresh_token_expires_at: null, expired: false, connected_at: null, last_error: null, last_error_at: null } }),
      );
      await g.route("**/api/onboarding/whatsapp/", (route) => route.fulfill({ json: { ...waReal, state: "close", done_at: null } }));
      await g.route("**/api/onboarding/whatsapp/qr/", (route) => route.fulfill({ json: { qr_base64: qr } }));
      await g.goto(`${BASE}/settings/claude`);
      await sleep(1500);
      await ready();
      await sleep(3500);
      await g.unroute("**/api/settings/claude/status/");
      await g.reload();
      await sleep(4000);
      await g.goto(`${BASE}/settings/whatsapp`);
      await sleep(2500);
      await g.getByRole("button", { name: "Mostrar QR" }).click();
      await sleep(6000);
      await g.unroute("**/api/onboarding/whatsapp/");
      await g.unroute("**/api/onboarding/whatsapp/qr/");
      await g.reload();
      await sleep(4000);
      await g.goto(`${BASE}/settings/style`);
      await sleep(3000);
      await scrollBy(g, 700, 14, 150);
      await sleep(3000);
    });
  });

  // 2. Orden mágica (Comercial): photo on item 1, text on item 2, Crear orden.
  await scene(browser, "02-orden-magica", async (part) => {
    await part([W], async ([c], ready) => {
      await login(c, "comercial");
      await c.goto(`${BASE}/orders/new`);
      await sleep(1500);
      await ready();
      await sleep(1500);
      const customer = c.getByPlaceholder("Busca por nombre o RUC");
      await customer.click();
      await customer.pressSequentially("Colegio Los Alg", { delay: 60 });
      await c.getByRole("option", { name: /Colegio Los Algarrobos/ }).first().click();
      await sleep(1000);
      const brand = c.locator("select").first();
      await brand.selectOption({ label: "UNICRACK" }).catch(() => null);
      await c.locator("input[type=date]").fill("2026-11-06");
      await sleep(800);
      // The file input is sr-only; the camera button only opens it.
      await c.getByRole("button", { name: "Foto de la prenda del ítem 1" }).hover();
      await sleep(600);
      await c.locator("input[type=file]").first().setInputFiles(PHOTO);
      mark("foto subida");
      const item1 = c.getByLabel("Ítem 1: la prenda como la pide el cliente");
      const deadline = Date.now() + 25_000;
      while (Date.now() < deadline && !(await item1.inputValue())) await sleep(500);
      mark(`descripción: ${await item1.inputValue()}`);
      await sleep(1500);
      const qty1 = c.getByLabel("Cantidad del ítem 1");
      await qty1.click();
      await qty1.pressSequentially("300", { delay: 120 });
      await qty1.press("Tab");
      await sleep(7000);
      await c.getByRole("button", { name: "Agregar ítem" }).click();
      await sleep(800);
      const item2 = c.getByLabel("Ítem 2: la prenda como la pide el cliente");
      await item2.click();
      await item2.pressSequentially("100 mandiles de cocina blancos con logo bordado", { delay: 45 });
      await item2.press("Tab");
      await sleep(14000);
      await scrollBy(c, 500, 8, 120);
      await sleep(2000);
      const create = c.getByRole("button", { name: /Crear orden/ });
      const until = Date.now() + 40_000;
      while (Date.now() < until && (await create.getAttribute("aria-disabled")) === "true") await sleep(500);
      await create.scrollIntoViewIfNeeded();
      await sleep(800);
      await create.click();
      await c.waitForURL(/\/orders\/\d+/, { timeout: 40_000 });
      state.orderUrl = new URL(c.url()).pathname;
      mark(`orden nueva: ${state.orderUrl}`);
      await sleep(5000);
      await scrollBy(c, 600, 10, 150);
      await sleep(3000);
    });
  });

  // 3. Producción revisa, ajusta por prompt y aprueba (needs the order of scene 2).
  await scene(browser, "03-produccion-ajusta", async (part) => {
    await part([W], async ([p], ready) => {
      await login(p, "produccion");
      if (!state.orderUrl) {
        const orders = await api(p, "/api/orders/", "produccion");
        const fresh = (Array.isArray(orders) ? orders : orders.results).find((o) => o.status === "broken_down" && o.code !== "CP-2026-0158");
        state.orderUrl = fresh ? `/orders/${fresh.id}` : "/orders";
      }
      await p.goto(`${BASE}/orders`);
      await sleep(1500);
      await ready();
      await sleep(3000);
      await p.goto(`${BASE}${state.orderUrl}`);
      await sleep(3500);
      const wand = p.getByRole("button", { name: "Ajustar con una instrucción" }).first();
      await wand.scrollIntoViewIfNeeded();
      await sleep(1000);
      await wand.click();
      await sleep(1200);
      const box = p.locator("dialog textarea, [role=dialog] textarea").first();
      await box.click();
      await box.pressSequentially("agrega 2 botones por polo y el corte toma 3 días", { delay: 45 });
      await sleep(600);
      await p.getByRole("button", { name: /^Proponer/ }).click();
      await p.getByRole("button", { name: "Aplicar" }).waitFor({ timeout: 40_000 });
      await sleep(4000);
      await p.getByRole("button", { name: "Aplicar" }).click();
      await sleep(5000);
      await p.mouse.wheel(0, -3000);
      await sleep(1200);
      const approve = p.getByRole("button", { name: "Aprobar y abastecer" }).first();
      if (await approve.isVisible().catch(() => false)) {
        await approve.click();
        await sleep(1200);
        await p.locator("dialog").getByRole("button", { name: "Aprobar y abastecer" }).click();
        await sleep(5000);
      } else {
        mark("no 'Aprobar y abastecer' button");
      }
    });
  });

  // 4. Inventario y pedido en lote (Producción), luego la aprobación del Gerente.
  await scene(browser, "04-pedido-en-lote", async (part) => {
    await part([W], async ([p], ready) => {
      await login(p, "produccion");
      await p.goto(`${BASE}/inventory`);
      await sleep(1500);
      await ready();
      await sleep(3000);
      await scrollBy(p, 400, 6, 150);
      await sleep(1500);
      await p.mouse.wheel(0, -2000);
      await sleep(800);
      await p.getByRole("button", { name: /^Por pedir/ }).first().click();
      await sleep(3000);
      await p.getByRole("button", { name: "Pedir todo" }).first().click();
      await sleep(2500);
      await p.locator("dialog").getByRole("button", { name: "Pedir todo" }).click();
      await waitText(p, "pedidos generados", 30_000);
      await sleep(5000);
    });
    await part([W], async ([g], ready) => {
      await login(g, "gerente");
      await g.goto(`${BASE}/`);
      await sleep(1500);
      await ready();
      await sleep(3500);
      const buttons = g.getByRole("button", { name: "Aprobar", exact: true });
      const n = await buttons.count();
      let target = null;
      for (let i = 0; i < n; i++) {
        const b = buttons.nth(i);
        const text = await b.evaluate((el) => (el.closest("section, article, li") ?? el.parentElement.parentElement.parentElement).innerText);
        if (!text.includes(REAL_SUPPLIER)) {
          target = b;
          break;
        }
      }
      if (!target) {
        mark("no approvable decision without the real supplier");
        return;
      }
      await target.scrollIntoViewIfNeeded();
      await sleep(2500);
      await target.click();
      await sleep(1500);
      await g.locator("dialog").getByRole("button", { name: "Aprobar" }).click();
      await waitText(g, "Enviando por WhatsApp", 10_000);
      await sleep(5000);
      await g.goto(`${BASE}/purchase-orders`);
      await sleep(5000);
    });
  });

  // 5. Proveedores medidos y matching (Gerente): cards, then the ranking modal. No approval.
  await scene(browser, "05-matching", async (part) => {
    await part([W], async ([g], ready) => {
      await login(g, "gerente");
      await g.goto(`${BASE}/suppliers`);
      await sleep(1500);
      await ready();
      await sleep(3000);
      await scrollBy(g, 900, 14, 160);
      await sleep(2500);
      await g.goto(`${BASE}/`);
      await sleep(4000);
      const change = g.getByRole("button", { name: "Cambiar proveedor" }).first();
      if (await change.isVisible().catch(() => false)) {
        await change.scrollIntoViewIfNeeded();
        await sleep(1500);
        await change.click();
        await sleep(7000);
        await g.getByRole("button", { name: "Cerrar", exact: true }).first().click();
        await sleep(2000);
      } else {
        mark("no 'Cambiar proveedor' on the Monitor");
        await sleep(5000);
      }
    });
  });

  // 6. WhatsApp en vivo: the supplier (simulator, right) answers; the purchase order (left) updates.
  await scene(browser, "06-whatsapp-en-vivo", async (part) => {
    await part([H, H], async ([po, sim], ready) => {
      await login(po, "gerente");
      await login(sim, "gerente");
      await po.goto(`${BASE}/purchase-orders/PI-0044`);
      await sim.goto(`${BASE}/simulator?present=1`);
      await sleep(1500);
      await ready();
      await sleep(3000);
      const contact = sim.locator("nav[aria-label='Contactos'] button").filter({ hasText: "Avíos Gamarra" }).filter({ hasNotText: "WhatsApp real" }).first();
      await contact.click();
      await sleep(3000);
      const bubbles = sim.getByText("Agente", { exact: true });
      const before = await bubbles.count();
      const box = sim.getByRole("textbox", { name: /Mensaje de/ });
      await box.click();
      await box.pressSequentially("Sí, el viernes 16 lo despacho por Sullana Express. Ya van 1500 de los 3430 listos", { delay: 40 });
      await sleep(800);
      await box.press("Enter");
      mark("mensaje del proveedor enviado");
      const deadline = Date.now() + 90_000;
      while (Date.now() < deadline && (await bubbles.count()) <= before) await sleep(1000);
      mark(`agente respondió: ${(await bubbles.count()) > before}`);
      await sleep(5000);
      await po.reload();
      await sleep(4000);
      await scrollBy(po, 700, 10, 150);
      await sleep(5000);
    });
  });

  // 7. Cancelación por el simulador (contacto simulado), avisos por rol y redistribución.
  await scene(browser, "07-avisos-por-rol", async (part) => {
    await part([H, H], async ([sim, c], ready) => {
      await login(sim, "gerente");
      await login(c, "comercial");
      await sim.goto(`${BASE}/simulator?present=1`);
      await c.goto(`${BASE}/`);
      await sleep(1500);
      await ready();
      await sleep(2500);
      await c.locator("header button[aria-expanded]").click();
      await sleep(1500);
      const contact = sim.locator("nav[aria-label='Contactos'] button").filter({ hasText: REAL_SUPPLIER }).filter({ hasNotText: "WhatsApp real" }).first();
      await contact.click();
      await sleep(2500);
      const bubbles = sim.getByText("Agente", { exact: true });
      const before = await bubbles.count();
      const box = sim.getByRole("textbox", { name: /Mensaje de/ });
      await box.click();
      await box.pressSequentially("Jefe, no voy a poder terminar. Se me malogró la máquina.", { delay: 45 });
      await sleep(800);
      await box.press("Enter");
      mark("cancelación enviada");
      const deadline = Date.now() + 90_000;
      while (Date.now() < deadline && (await bubbles.count()) <= before) await sleep(1000);
      mark(`agente respondió: ${(await bubbles.count()) > before}`);
      await sleep(8000);
      await waitText(c, "peligro", 60_000);
      await sleep(6000);
    });
    await part([W], async ([g], ready) => {
      await login(g, "gerente");
      await g.goto(`${BASE}/`);
      await sleep(1500);
      await ready();
      const deadline = Date.now() + 60_000;
      while (Date.now() < deadline && !(await g.getByText("Redistribuci").first().isVisible().catch(() => false))) {
        await sleep(5000);
        await g.reload();
        await sleep(3000);
      }
      const card = g.getByText("Redistribuci").first();
      if (await card.isVisible().catch(() => false)) {
        await card.scrollIntoViewIfNeeded();
        await sleep(6000);
        const route = g.getByRole("link", { name: "Ver la ruta nueva" }).first();
        if (await route.isVisible().catch(() => false)) {
          await route.click();
          await g.waitForURL(/\/routes/, { timeout: 15_000 });
          await sleep(9000);
        }
      } else {
        mark("no Redistribución card on the Monitor");
        await sleep(4000);
      }
    });
  });

  // 7b. Redistribución (Gerente): the decision card of CP-2026-0142 after the
  // cancellation, with "Ver la ruta nueva". Recorded on its own and appended to 07.
  await scene(browser, "07b-redistribucion", async (part) => {
    await part([W], async ([g], ready) => {
      await login(g, "gerente");
      await g.goto(`${BASE}/`);
      await sleep(1500);
      await ready();
      await sleep(3000);
      const route = g.getByRole("link", { name: "Ver la ruta nueva" }).first();
      await route.scrollIntoViewIfNeeded();
      await sleep(7000);
      await route.click();
      await g.waitForURL(/\/routes/, { timeout: 15_000 });
      await sleep(10000);
    });
  });

  // 8. Rutas y flota en vivo (Producción). Leaves the simulation stopped.
  await scene(browser, "08-rutas", async (part) => {
    await part([W], async ([p], ready) => {
      await login(p, "produccion");
      await p.goto(`${BASE}/routes`);
      await sleep(1500);
      await ready();
      await sleep(4000);
      await p.getByRole("button", { name: /planificar el día/i }).first().click();
      await sleep(6000);
      const tomorrow = p.getByRole("button", { name: "Pasar a mañana" }).first();
      if (await tomorrow.isVisible().catch(() => false)) {
        await tomorrow.scrollIntoViewIfNeeded();
        await sleep(1500);
        await tomorrow.click();
        await sleep(2500);
      }
      await p.mouse.wheel(0, -3000);
      await sleep(800);
      await p.getByRole("tab", { name: "En vivo" }).click();
      await sleep(3000);
      const start = p.getByRole("button", { name: "Iniciar ruta" }).first();
      if (await start.isVisible().catch(() => false)) {
        await start.click();
        await sleep(2500);
      }
      const simulate = p.getByRole("button", { name: "Simular", exact: true }).first();
      if (await simulate.isVisible().catch(() => false)) {
        await simulate.click();
        mark("simulación iniciada");
        await sleep(28000);
        await p.getByRole("button", { name: "Detener simulación" }).first().click().catch(() => mark("no Detener simulación"));
        await sleep(2500);
      } else {
        mark("no 'Simular' button");
        await sleep(5000);
      }
    });
  });

  await browser.close();
  writeFileSync(`${RAW}log.txt`, log.join("\n") + "\n");
  mark("done");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
