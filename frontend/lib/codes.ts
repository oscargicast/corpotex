// Business codes the assistant writes instead of URLs (ASSISTANT_RULES).
// Orders keep Comercial's code (CP-2026-0001); purchase orders are
// PT- (workshop), PI- (material) or PF- (finished product) plus 4 digits.
export const CODE_PATTERN = /\b(CP-[A-Z0-9-]+|P[TIF]-\d{4})\b/g;

// Detail pages accept a code and resolve it with ?code=.
export function hrefForCode(code: string): string {
  return code.startsWith("CP-") ? `/orders/${code}` : `/purchase-orders/${code}`;
}
