#!/bin/sh
# Starts Xvfb explicitly instead of wrapping the app in `xvfb-run` --
# xvfb-run signals readiness to its parent via SIGUSR1, which is unreliable
# when that parent is PID 1 inside a container (confirmed the hard way:
# xvfb-run hung forever waiting for a signal that never arrived, Xvfb
# itself was up the whole time). Polling for the X11 socket file is a
# plainer, more debuggable way to know the display is actually ready.
set -e

# A restart of the SAME container (restart: unless-stopped after a crash/OOM,
# `docker restart`) reuses its filesystem, so the previous run's X lock and
# socket are still in /tmp -- Xvfb then refuses to start ("Server is already
# active for display 99", confirmed live) while the entrypoint's socket wait
# below passes on the stale socket file, so Flask came up looking healthy
# but every browser launch failed with "Missing X server or $DISPLAY".
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
# Same story for PulseAudio's system-mode state: its pid file survives the
# restart, and the old PID can be reused by an unrelated live process in the
# fresh PID namespace, so `pulseaudio -D` below fails with "Daemon startup
# failed" and `set -e` turns that into a restart loop (confirmed live).
rm -f /var/run/pulse/pid /var/run/pulse/native
rm -rf /tmp/pulse-*

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY=:99

for i in $(seq 1 30); do
  [ -e /tmp/.X11-unix/X99 ] && break
  sleep 0.5
done
# Fail loudly here (container restarts, logs show why) instead of serving a
# Flask app whose bots can never open a browser.
if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "Xvfb exited during startup" >&2
  exit 1
fi

# The container has no real audio hardware (no /dev/snd) at all, but Chrome
# still needs a working PulseAudio server to route through for the "audio"
# half of getDisplayMedia's tab capture -- without one, that combined
# video+audio request fails outright with "NotReadableError: Could not
# start video source" (confirmed live on a Zoom join; the error blames
# "video" but it's the missing audio sink taking the whole stream down).
# A null sink is enough since nothing is meant to play through real
# speakers here, just give Chrome's tab-audio capture something to attach to.
# --system: this container runs as root and PulseAudio refuses to start as
# root at all otherwise. Normally discouraged (system-wide mode is meant to
# be run as a dedicated non-root user), but acceptable here -- the whole
# point of this container is one isolated, single-purpose process, not a
# shared multi-user audio server.
pulseaudio --system --disallow-exit --exit-idle-time=-1 -D
for i in $(seq 1 30); do
  pactl info >/dev/null 2>&1 && break
  sleep 0.5
done
pactl load-module module-null-sink sink_name=DummyOutput
pactl set-default-sink DummyOutput
# Without this the sink goes to sleep after 5 s of silence and its monitor stops delivering
# data, which would leave holes in the backup audio capture (bots/audio_backup.py).
pactl unload-module module-suspend-on-idle || true

exec "$@"
