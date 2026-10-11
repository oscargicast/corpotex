// Per-browser conveniences of the assistant's notices (P7): the chime, its
// mute switch and the notices hidden from the chat. Storage may be blocked;
// everything still works, it just is not remembered.

const MUTED_KEY = "corpotex.assistant.muted";
const HIDDEN_KEY = "corpotex.assistant.hiddenNotices";
const HIDDEN_LIMIT = 300;

let audio: AudioContext | null = null;

// Two short rising tones (~200 ms) made with Web Audio: no file to load. The
// chat only plays it after the user opened it, so the page already has the
// user activation browsers ask for.
export function playChime(): void {
  try {
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Context) return;
    audio ??= new Context();
    const ctx = audio;
    if (ctx.state === "suspended") void ctx.resume();
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
    // No audio (blocked or unsupported): the notice still shows.
  }
}

export function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTED_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeMuted(muted: boolean): void {
  try {
    localStorage.setItem(MUTED_KEY, muted ? "1" : "0");
  } catch {
    // Not remembered.
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
