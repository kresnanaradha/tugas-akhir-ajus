# The base image tag's own bundled Chromium build can drift behind the
# exact pip `playwright` version pinned in requirements.txt even when both
# claim the same version number (confirmed live: v1.63.0-noble shipped
# chromium-1234, pip's playwright==1.63.0 wanted chromium-1243) --
# BrowserType.launch then fails with "Executable doesn't exist". The base
# image still supplies every system library Playwright's browsers need, so
# `playwright install chromium` below only has to fetch the browser itself,
# not --with-deps.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# xvfb: a virtual display. The bot launches Chrome headed (headless=False),
# not headless — getDisplayMedia() tab capture doesn't work reliably
# headless (see CLAUDE.md's "Known accepted limitation"). Without a real or
# virtual display, a headed Chrome has nowhere to render at all. Inside a
# container there's no physical monitor, so Xvfb stands in for one — this
# is also what makes the bot's browser window invisible on the host
# machine's own screen, unlike running it directly on Windows.
# ffmpeg: whisperx's audio loader shells out to it.
# DEBIAN_FRONTEND=noninteractive: pulseaudio's postinst can otherwise stall
# waiting on a debconf prompt with no tty attached to answer it -- confirmed
# live, a build hung 15+ minutes with zero output once pulseaudio was added.
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb ffmpeg pulseaudio pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/* \
    # PulseAudio's own package creates a "pulse-access" group and only lets
    # members of it connect to a --system-mode daemon -- root isn't exempt
    # by default. Without this, pactl/Chrome both got "Connection failure:
    # Access denied" and the whole entrypoint crash-looped (confirmed live).
    && usermod -aG pulse-access root

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 5050

# Also unbuffers Python's stdout -- without this, `docker logs` shows
# nothing for a long time (print() output sits in a buffer until it's
# full), which made an earlier startup hang much harder to diagnose than
# it needed to be.
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "app.py"]
