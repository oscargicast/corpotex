// Garment photo for the magic order (ADR 0028 §3b): shrunk in the browser
// before POST /api/orders/describe-image/, never saved with the order.

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_SIDE = 1568; // long side, px
const QUALITIES = [0.85, 0.7, 0.55]; // JPEG; the next one only if over the upload limit
const MAX_INPUT_BYTES = 25 * 1024 * 1024;
const MAX_UPLOAD_CHARS = 5 * 1024 * 1024; // the API's limit is on the base64 itself (ADR 0028 §3b)

export interface GarmentPhoto {
  url: string; // data URL of the shrunk JPEG, for the thumbnail
  data: string; // the same JPEG in base64, without the data: prefix
}

export class PhotoError extends Error {}

// The first image of a paste or a drop, if any.
export function imageFrom(list: FileList | DataTransferItemList | null | undefined): File | null {
  if (!list) return null;
  for (const entry of Array.from(list as ArrayLike<File | DataTransferItem>)) {
    const file = entry instanceof File ? entry : entry.kind === "file" ? entry.getAsFile() : null;
    if (file && file.type.startsWith("image/")) return file;
  }
  return null;
}

async function decode(file: Blob): Promise<{ source: CanvasImageSource; width: number; height: number; close: () => void }> {
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    return { source: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.src = url;
  await img.decode();
  return { source: img, width: img.naturalWidth, height: img.naturalHeight, close: () => URL.revokeObjectURL(url) };
}

// Long side at most 1568 px, JPEG at 85 % (less only to stay under 5 MB).
export async function shrinkPhoto(file: File): Promise<GarmentPhoto> {
  if (!PHOTO_TYPES.includes(file.type)) throw new PhotoError("Usa una foto JPG, PNG o WebP.");
  if (file.size > MAX_INPUT_BYTES) throw new PhotoError("La foto pesa demasiado. Usa una de menos de 25 MB.");
  let image;
  try {
    image = await decode(file);
  } catch {
    throw new PhotoError("No se pudo leer la foto. Prueba con otra.");
  }
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(image.width, image.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new PhotoError("No se pudo preparar la foto.");
    // JPEG has no transparency: a white background for PNG and WebP.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image.source, 0, 0, canvas.width, canvas.height);
    for (const quality of QUALITIES) {
      const url = canvas.toDataURL("image/jpeg", quality);
      const data = url.slice(url.indexOf(",") + 1);
      if (data.length <= MAX_UPLOAD_CHARS) return { url, data };
    }
    throw new PhotoError("La foto sigue pesando más de 5 MB. Prueba con otra.");
  } finally {
    image.close();
  }
}
