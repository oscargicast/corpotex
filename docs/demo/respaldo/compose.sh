#!/bin/zsh
# Stitch the segments recorded by record.mjs into one 1920x1080 H.264 mp4, no audio.
#   compose.sh [out.mp4]
# Two-window segments (NAME-0 and NAME-1, 960x1080 each) go side by side; single
# ones are scaled or padded to 1920x1080. SPEED_<NN>=factor speeds up a segment
# (e.g. SPEED_03=2 halves the agent wait); CUT_<NN>="start,end" drops that span.
set -euo pipefail
cd "$(dirname "$0")/out"
out="${1:-$HOME/Desktop/corpotex-demo-respaldo.mp4}"
tmp=$(mktemp -d)
parts=()

first_webm() { local f=("$1"/*.webm(N)); echo "${f[1]:-}"; }

for dir0 in $(ls -d *-0 | sort); do
  name="${dir0%-0}"
  num="${name%%-*}"
  a=$(first_webm "$dir0"); [ -n "$a" ] || continue
  b=$(first_webm "${name}-1")
  part="$tmp/$name.mp4"
  speed_var="SPEED_$num"; speed="${(P)speed_var:-1}"
  cut_var="CUT_$num"; cut="${(P)cut_var:-}"
  # Trim: drop [start,end) seconds by keeping the two sides.
  trim=""
  if [ -n "$cut" ]; then
    s="${cut%%,*}"; e="${cut##*,}"
    trim="select='not(between(t,$s,$e))',setpts=N/FRAME_RATE/TB,"
  fi
  pts="setpts=PTS/$speed"
  if [ -n "$b" ]; then
    ffmpeg -v error -y -i "$a" -i "$b" -filter_complex \
      "[0:v]scale=960:1080,${trim}${pts}[l];[1:v]scale=960:1080,${trim}${pts}[r];[l][r]hstack=inputs=2,fps=25,format=yuv420p[v]" \
      -map "[v]" -c:v libx264 -preset veryfast -crf 20 -an "$part"
  else
    ffmpeg -v error -y -i "$a" -filter_complex \
      "[0:v]${trim}${pts},scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#15141c,fps=25,format=yuv420p[v]" \
      -map "[v]" -c:v libx264 -preset veryfast -crf 20 -an "$part"
  fi
  parts+=("$part")
  printf '%s %.1fs\n' "$name" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$part")"
done

list="$tmp/list.txt"; : > "$list"
for p in "${parts[@]}"; do echo "file '$p'" >> "$list"; done
ffmpeg -v error -y -f concat -safe 0 -i "$list" -c copy -movflags +faststart "$out"
printf 'total %.1fs -> %s\n' "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out")" "$out"
rm -rf "$tmp"
