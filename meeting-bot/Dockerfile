# Base image already has Chromium matching the exact Playwright version
# pinned in requirements.txt (see the comment there) and every system
# library Playwright's browsers need — skips a separate
# `playwright install chromium` step and avoids a version mismatch between
# the Python package and the browser binary.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

# xvfb: a virtual display. The bot launches Chrome headed (headless=False),
# not headless — getDisplayMedia() tab capture doesn't work reliably
# headless (see CLAUDE.md's "Known accepted limitation"). Without a real or
# virtual display, a headed Chrome has nowhere to render at all. Inside a
# container there's no physical monitor, so Xvfb stands in for one — this
# is also what makes the bot's browser window invisible on the host
# machine's own screen, unlike running it directly on Windows.
# ffmpeg: whisperx's audio loader shells out to it.
RUN apt-get update && apt-get install -y --no-install-recommends xvfb ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
