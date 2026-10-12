# syntax=docker/dockerfile:1

# ---------- Estágio 1: compila o frontend Vue (não vai para a imagem final) ----------
FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Estágio 2: runtime Python mínimo ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# FFmpeg para análise/transcodificação/legendas
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Usuário sem privilégios, sem shell de login e sem home
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Código e frontend pertencem ao root: o processo (uid 10001) só consegue LER.
COPY backend/app ./app
COPY --from=frontend /build/dist ./static

# Único diretório gravável (volume com cache, progresso e legendas)
RUN mkdir -p /data && chown app:app /data && chmod 700 /data

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--loop", "uvloop", "--http", "httptools", "--no-server-header", "--no-access-log"]
