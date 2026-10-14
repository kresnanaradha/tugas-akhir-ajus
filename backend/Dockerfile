# Chromium bawaan image dasar bisa berbeda build dengan yang diminta playwright==1.63.0 dari pip (chromium-1234
# lawan 1243), lalu peluncuran gagal dengan "Executable doesn't exist". Image tetap punya semua library sistem, jadi
# `playwright install chromium` di bawah hanya mengunduh browsernya (tanpa --with-deps)
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# xvfb: display virtual. Bot menjalankan Chrome dengan tampilan (tab capture tidak andal tanpa tampilan, lihat CLAUDE.md) dan
# container tidak punya monitor. Ini juga menjaga jendelanya dari layar host.
# ffmpeg: dipakai pemuat audio whisperx.
# DEBIAN_FRONTEND=noninteractive: instalasi pulseaudio menunggu prompt debconf tanpa tty (build pernah macet 15+ menit)
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb ffmpeg pulseaudio pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/* \
    # PulseAudio hanya mengizinkan anggota pulse-access terhubung ke daemon --system, termasuk root, kalau tidak pactl dan
    # Chrome mendapat "Access denied" dan entrypoint crash-loop
    && usermod -aG pulse-access root

WORKDIR /app

# kosong (default): whisperx menarik torch CUDA (~2.8.0+cu128) padahal mesin ini tidak punya GPU. Isi 1 untuk memasang
# wheel CPU lebih dulu, supaya instalasi whisperx sendiri terpenuhi olehnya (pip tidak mengganti paket yang
# sudah memenuhi). worker-1..10 tetap default
ARG TORCH_CPU=
# torchvision dan torchaudio juga: transformers menarik torchvision, pyannote menarik torchaudio, dan keduanya ekstensi native
# yang dibangun untuk satu torch tertentu. Dibiarkan ke pip mereka mendapat versi yang tidak cocok ABI ("operator torchvision::nms
# does not exist", "libtorch_cuda.so: cannot open shared object file"). 0.23.0 / 2.8.0 cocok dengan torch 2.8.0
RUN if [ -n "$TORCH_CPU" ]; then \
      pip install --no-cache-dir torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 5050

# stdout tanpa buffer, kalau tidak `docker logs` tidak menampilkan apa-apa lama (ini membuat startup yang macet sulit didiagnosis)
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "app.py"]
