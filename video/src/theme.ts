import { loadFont } from "@remotion/google-fonts/Inter";

// Corpotex tokens (frontend/app/globals.css). Orange only for the primary accent.
export const colors = {
  brand: "#ff8c06",
  accent: "#0062fa",
  ink: "#15141c",
  inkSoft: "#23222c",
  muted: "#a3a2ad",
  line: "#2f2e38",
  canvas: "#f5f5f7",
  surface: "#ffffff",
  success: "#2fbf6b",
  danger: "#ff6b5e",
};

const inter = loadFont("normal", {
  weights: ["400", "600", "800"],
  subsets: ["latin"],
});

export const fontFamily = inter.fontFamily;
