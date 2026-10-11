// The assistant's notices (P7): a chime when one arrives while the chat is
// open, always on (Oscar 11/10), and the notices hidden from the chat in this
// browser. Storage may be blocked; everything still works, it just is not
// remembered.

const HIDDEN_KEY = "corpotex.assistant.hiddenNotices";
const HIDDEN_LIMIT = 300;

// Browsers only let audio start from a user gesture. The context is created
// (or resumed) inside the first click, touch or key press on the page, never
// before, so no autoplay warning reaches the console. Until then a notice
// simply does not sound.
let audio: AudioContext | null = null;

function unlockAudio(): void {
  try {
    if (!audio) {
      const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Context) return;
      audio = new Context();
    }
    if (audio.state === "suspended") void audio.resume().catch(() => undefined);
  } catch {
    // No audio on this browser: the notice still shows.
  }
}

// Armed when the app loads (this module comes with the shell), so the very
// click that opens the chat already counts as the gesture.
if (typeof window !== "undefined") {
  for (const type of ["pointerdown", "keydown", "touchstart"] as const) {
    window.addEventListener(type, unlockAudio, { capture: true, passive: true });
  }
}

// Two short rising tones (~200 ms) made with Web Audio: no file to load.
export function playChime(): void {
  const ctx = audio;
  if (!ctx || ctx.state !== "running") return; // No gesture yet (or audio blocked): silent.
  try {
    const start = ctx.currentTime + 0.01;
    for (const [frequency, offset] of [
      [880, 0],
      [1318.5, 0.1],
    ] as const) {
      const tone = ctx.createOscillator();
      const gain = ctx.createGain();
      tone.type = "sine";
      tone.frequency.value = frequency;
      // A soft envelope: no click at either end.
      gain.gain.setValueAtTime(0.0001, start + offset);
      gain.gain.exponentialRampToValueAtTime(0.16, start + offset + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.1);
      tone.connect(gain).connect(ctx.destination);
      tone.start(start + offset);
      tone.stop(start + offset + 0.11);
    }
  } catch {
    // The notice still shows.
  }
}

export function readHidden(): Set<number> {
  try {
    const ids: unknown = JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]");
    return new Set(Array.isArray(ids) ? ids.filter((id): id is number => typeof id === "number") : []);
  } catch {
    return new Set();
  }
}

export function writeHidden(ids: Set<number>): void {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...ids].slice(-HIDDEN_LIMIT)));
  } catch {
    // Hidden for this visit only.
  }
}
