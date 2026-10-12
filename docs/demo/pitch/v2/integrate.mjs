// Inline the feature fragments (features/NN-slug.html) into index.html, replacing
// whatever sits between <!-- features:start --> and <!-- features:end -->.
// A slot without a fragment yet keeps a placeholder, so the deck always has 11 slides.
import { readdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const SLOTS = [
  ["05", "orden-magica", "Orden mágica: se reconoce mientras Comercial escribe"],
  ["06", "ficha-tecnica", "Ficha técnica y ruta crítica: se ajustan con una instrucción"],
  ["07", "pedido-en-lote", "Pedido en lote: una compra por proveedor, con justificación"],
  ["08", "whatsapp-en-vivo", "WhatsApp en vivo: el agente habla como el Gerente"],
  ["09", "cancelacion-redistribucion", "Un taller cancela: el sistema redistribuye y avisa"],
  ["10", "rutas-flota", "Rutas y flota en vivo, capacidad de planta"],
];

const here = new URL(".", import.meta.url).pathname;
const index = join(here, "index.html");
const dir = join(here, "features");
const present = existsSync(dir) ? readdirSync(dir).filter((f) => /^\d\d-.*\.html$/.test(f)) : [];
const parts = SLOTS.map(([nn, slug, title]) => {
  const file = `${nn}-${slug}.html`;
  if (present.includes(file)) return `<!-- ${file} -->\n${readFileSync(join(dir, file), "utf8").trim()}`;
  return `<section class="slide feature" data-feature="${slug}"><div class="ph"><b>${title}</b>fragmento de disenador · features/${file}</div><div class="pg">${nn}</div></section>`;
});
const html = readFileSync(index, "utf8");
const start = "<!-- features:start -->";
const end = "<!-- features:end -->";
const a = html.indexOf(start), b = html.indexOf(end);
if (a < 0 || b < 0) throw new Error("markers not found in index.html");
writeFileSync(index, html.slice(0, a + start.length) + "\n" + parts.join("\n\n") + "\n" + html.slice(b));
const done = SLOTS.filter(([nn, slug]) => present.includes(`${nn}-${slug}.html`)).map(([nn]) => nn);
console.log(`slots 05-10: inlined ${done.join(", ") || "none"}; placeholders for ${SLOTS.filter(([nn]) => !done.includes(nn)).map(([nn]) => nn).join(", ") || "none"}`);
