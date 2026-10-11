// Business codes the assistant writes instead of URLs (ASSISTANT_RULES).
// Orders keep Comercial's code (CP-2026-0001 in the examples, OC-2026-0151 in
// Kenji's seed); purchase orders are PT-/PI-/PF- plus 4 digits, or PED-0027 in
// the seed. Both spellings link until backend settles on one.
const ORDER_PREFIX = /^(CP|OC)-/;
export const CODE_PATTERN = /\b((?:CP|OC)-[A-Z0-9-]+|(?:P[TIF]|PED)-\d{4})\b/g;

// Detail pages accept a code and resolve it with ?code=.
export function hrefForCode(code: string): string {
  return ORDER_PREFIX.test(code) ? `/orders/${code}` : `/purchase-orders/${code}`;
}
