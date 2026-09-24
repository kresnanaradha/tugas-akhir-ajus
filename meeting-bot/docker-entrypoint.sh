#!/bin/sh
# Starts Xvfb explicitly instead of wrapping the app in `xvfb-run` --
# xvfb-run signals readiness to its parent via SIGUSR1, which is unreliable
# when that parent is PID 1 inside a container (confirmed the hard way:
# xvfb-run hung forever waiting for a signal that never arrived, Xvfb
# itself was up the whole time). Polling for the X11 socket file is a
# plainer, more debuggable way to know the display is actually ready.
set -e

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
export DISPLAY=:99

for i in $(seq 1 30); do
  [ -e /tmp/.X11-unix/X99 ] && break
  sleep 0.5
done

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

exec "$@"
