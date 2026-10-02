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

# Unset (default): whisperx pulls in torch unpinned, which resolves to a
# CUDA build (~confirmed 2.8.0+cu128, bundling the full CUDA runtime) even
# though this box has no GPU (compute_type="int8" on faster-whisper is what
# actually runs transcription — see CLAUDE.md). Set to 1 (worker-test only,
# see docker-compose.yml) to install the CPU-only wheel FIRST so whisperx's
# own install afterward is satisfied by it instead of pulling CUDA — the
# standard trick for this, since pip won't replace an already-satisfying
# package. worker-1..10 stay on the default (unset) so nothing about their
# already-working image changes.
ARG TORCH_CPU=
# torchvision AND torchaudio too, not just torch: sentence-transformers/
# transformers pull in torchvision transitively, pyannote (diarization)
# pulls in torchaudio -- both are native extensions compiled against one
# exact torch build, and leaving pip to grab either on its own resolved an
# ABI-incompatible version each time ("RuntimeError: operator
# torchvision::nms does not exist", then separately "OSError:
# libtorch_cuda.so: cannot open shared object file" from torchaudio --
# both confirmed live, torchaudio only surfacing once diarization actually
# ran). 0.23.0 / 2.8.0 are torch 2.8.0's matched releases.
RUN if [ -n "$TORCH_CPU" ]; then \
      pip install --no-cache-dir torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu; \
    fi

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
