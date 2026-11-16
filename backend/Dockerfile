# Chromium bawaan image dasar bisa berbeda build dengan yang diminta playwright==1.63.0 dari pip (chromium-1234
# lawan 1243), lalu peluncuran gagal dengan "Executable doesn't exist". Image tetap punya semua library sistem, jadi
# `playwright install chromium` di bawah hanya mengunduh browsernya (tanpa --with-deps)
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# xvfb: display virtual. Bot menjalankan Chrome dengan tampilan (tab capture tidak andal tanpa tampilan, lihat CLAUDE.md) dan
# container tidak punya monitor. Ini juga menjaga jendelanya dari layar host.
# ffmpeg: perekaman audio cadangan (bots/audio_backup.py) dan ffprobe untuk memetakan waktu audio ke video.
# DEBIAN_FRONTEND=noninteractive: instalasi pulseaudio menunggu prompt debconf tanpa tty (build pernah macet 15+ menit)
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb ffmpeg pulseaudio pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/* \
    # PulseAudio hanya mengizinkan anggota pulse-access terhubung ke daemon --system, termasuk root, kalau tidak pactl dan
    # Chrome mendapat "Access denied" dan entrypoint crash-loop
    && usermod -aG pulse-access root

WORKDIR /app

# torch hanya untuk sentence-transformers (embedding Knowledge Base). Mesin ini tidak punya GPU, jadi wheel CPU dipasang lebih
# dulu supaya pip tidak menarik torch CUDA yang jauh lebih besar (pip tidak mengganti paket yang sudah memenuhi syarat)
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

# x11vnc + novnc + websockify: melihat display Xvfb dari browser (http://localhost:6080/vnc.html) untuk login akun Google
# bot di dalam container (bots/google_login_vnc.py), hanya dinyalakan kalau VNC_PASSWORD diisi (docker-entrypoint.sh).
# Dipasang SETELAH pip: paket apt ini membawa paket Python versi Ubuntu yang tidak bisa diganti pip (uninstall-no-record-file)
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends x11vnc novnc websockify \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 5050 6080

# stdout tanpa buffer, kalau tidak `docker logs` tidak menampilkan apa-apa lama (ini membuat startup yang macet sulit didiagnosis)
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
