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

exec "$@"
