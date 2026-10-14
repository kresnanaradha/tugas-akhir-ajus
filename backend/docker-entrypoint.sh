#!/bin/sh
# Xvfb dijalankan manual, bukan `xvfb-run`: xvfb-run memberi tahu kesiapan lewat SIGUSR1, yang macet kalau induknya
# PID 1 di container. Menunggu socket X11 lebih sederhana
set -e

# restart container yang sama mempertahankan filesystem-nya, jadi lock dan socket X lama masih ada di /tmp: Xvfb menolak
# mulai ("Server is already active for display 99") sementara penantian socket di bawah lolos oleh file basi, dan setiap
# peluncuran browser gagal dengan "Missing X server or $DISPLAY"
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
# sama untuk state PulseAudio: file pid bertahan setelah restart dan PID lama bisa dipakai proses lain sekarang, jadi
# `pulseaudio -D` gagal dan `set -e` mengubahnya jadi loop restart
rm -f /var/run/pulse/pid /var/run/pulse/native
rm -rf /tmp/pulse-*

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY=:99

for i in $(seq 1 30); do
  [ -e /tmp/.X11-unix/X99 ] && break
  sleep 0.5
done
# gagal di sini (container restart dan log menjelaskan sebabnya) daripada menyajikan Flask yang botnya tidak bisa membuka browser
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "Xvfb exited during startup" >&2
  exit 1
fi

# tidak ada hardware audio di sini, tapi Chrome butuh server PulseAudio yang jalan untuk bagian audio getDisplayMedia, kalau tidak
# permintaan gabungannya gagal dengan "NotReadableError: Could not start video source" (errornya menyalahkan video). Null sink
# cukup. --system karena container ini jalan sebagai root dan PulseAudio menolak start sebagai root kalau tidak, tidak apa-apa
# untuk container satu tujuan
pulseaudio --system --disallow-exit --exit-idle-time=-1 -D
for i in $(seq 1 30); do
  pactl info >/dev/null 2>&1 && break
  sleep 0.5
done
pactl load-module module-null-sink sink_name=DummyOutput
pactl set-default-sink DummyOutput
# tanpa ini sink tertidur setelah 5 detik hening dan monitornya berhenti mengirim data, meninggalkan lubang di audio cadangan
# (bots/audio_backup.py)
pactl unload-module module-suspend-on-idle || true

exec "$@"
