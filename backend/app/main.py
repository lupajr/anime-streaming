"""API FastAPI: biblioteca, streaming (proxy com Range) e frontend estático."""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import get_settings
from .db import DB
from .drive import DriveClient, DriveError
from .library import Library, LibraryError
from .media import MediaError, MediaService
from .security import SecurityHeadersMiddleware

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("app")

RANGE_RE = re.compile(r"^bytes=\d*-\d*$")
DIRECT_MIME = {
    ".mkv": "video/x-matroska", ".webm": "video/webm", ".mp4": "video/mp4",
    ".m4v": "video/mp4", ".mov": "video/quicktime", ".avi": "video/x-msvideo", ".ts": "video/mp2t",
}
IMAGE_MAX_BYTES = 8 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    data_dir = Path(settings.data_dir)
    (data_dir / "images").mkdir(parents=True, exist_ok=True)
    db = DB(data_dir / "anime.db")
    drive = DriveClient(settings.google_credentials_file)
    app.state.db = db
    app.state.drive = drive
    app.state.library = Library(db, drive, settings)
    app.state.media = MediaService(drive, db, settings)
    email = drive.service_account_email
    if email:
        log.info("Service account: %s", email)
    else:
        log.error("Credencial não encontrada/ inválida em %s", settings.google_credentials_file)
    yield
    await app.state.media.shutdown()
    await drive.aclose()


app = FastAPI(
    title="Anime Streaming",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(LibraryError)
@app.exception_handler(MediaError)
@app.exception_handler(DriveError)
async def domain_error_handler(_: Request, exc: Exception):
    status = getattr(exc, "status", 500)
    if status not in (400, 404, 413, 416, 429, 502, 503, 504):
        status = 502
    return JSONResponse({"detail": str(exc)}, status_code=status)


def lib(request: Request) -> Library:
    return request.app.state.library


def media(request: Request) -> MediaService:
    return request.app.state.media


# --------------------------------------------------------------------- API
@app.get("/api/health")
async def health(request: Request):
    return {"status": "ok", "service_account": request.app.state.drive.service_account_email}


@app.get("/api/stats")
async def stats(request: Request):
    drive: DriveClient = request.app.state.drive
    return {
        "drive_api_calls": dict(drive.calls),
        "drive_api_total": sum(drive.calls.values()),
        **media(request).stats(),
    }


@app.get("/api/folders/{folder_id}")
async def get_folder(folder_id: str, request: Request):
    library = lib(request)
    await library.ensure_fresh()
    return library.folder_view(folder_id)


@app.post("/api/library/refresh")
async def refresh_library(request: Request):
    await lib(request).refresh()
    return {"ok": True}


@app.get("/api/files/{file_id}")
async def get_file(file_id: str, request: Request):
    library = lib(request)
    await library.ensure_fresh()
    return library.file_view(file_id)


@app.get("/api/continue")
async def continue_watching(request: Request):
    library = lib(request)
    await library.ensure_fresh()
    return library.continue_watching()


class ProgressIn(BaseModel):
    position: float = Field(ge=0, le=86400)
    duration: float = Field(ge=0, le=86400)


@app.put("/api/progress/{file_id}")
async def put_progress(file_id: str, body: ProgressIn, request: Request):
    lib(request).save_progress(file_id, body.position, body.duration)
    return {"ok": True}


@app.delete("/api/progress/{file_id}")
async def delete_progress(file_id: str, request: Request):
    lib(request).clear_progress(file_id)
    return {"ok": True}


@app.get("/api/media/{file_id}/info")
async def media_info(file_id: str, request: Request):
    item = lib(request).item(file_id, "video")
    return await media(request).probe(item)


@app.get("/api/media/{file_id}/keyframe")
async def media_keyframe(file_id: str, request: Request, t: float = Query(ge=0, le=86400)):
    item = lib(request).item(file_id, "video")
    return {"t": await media(request).keyframe_before(item, t)}


@app.get("/api/media/{file_id}/subtitles/{index}")
async def media_subtitle(file_id: str, index: int, request: Request):
    item = lib(request).item(file_id, "video")
    info = await media(request).probe(item)
    text, complete = media(request).subtitle(item, info, index)
    return Response(
        text,
        media_type="text/vtt; charset=utf-8",
        headers={"X-Subtitle-Complete": "1" if complete else "0", "Cache-Control": "no-store"},
    )


@app.get("/api/stream/{file_id}")
async def stream_direct(file_id: str, request: Request):
    """Proxy de streaming: repassa o Range para o Drive e devolve 206 Partial Content."""
    item = lib(request).item(file_id, "video")
    range_header = request.headers.get("range")
    if range_header and not RANGE_RE.fullmatch(range_header.strip()):
        raise HTTPException(416, "Range inválido")

    upstream = await request.app.state.drive.open_media(file_id, range_header)
    if upstream.status_code not in (200, 206):
        status = upstream.status_code
        await upstream.aclose()
        log.warning("Drive media %s -> %s", file_id, status)
        raise HTTPException(416 if status == 416 else 502, "Falha ao obter o vídeo do Drive")

    headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
    for name in ("content-length", "content-range"):
        if name in upstream.headers:
            headers[name] = upstream.headers[name]
    media_type = DIRECT_MIME.get(Path(item["name"]).suffix.lower(), "application/octet-stream")

    async def body():
        try:
            async for chunk in upstream.aiter_raw(256 * 1024):
                yield chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(body(), status_code=upstream.status_code, headers=headers, media_type=media_type)


@app.get("/api/transcode/{file_id}")
async def stream_transcode(
    file_id: str,
    request: Request,
    start: float = Query(0, ge=0, le=86400),
    audio: int = Query(0, ge=0, le=64),
    burn: int | None = Query(None, ge=0, le=64),
):
    """Modo compatível: remux/transcodifica para MP4 fragmentado (H.264 + AAC)."""
    item = lib(request).item(file_id, "video")
    service = media(request)
    info = await service.probe(item)
    if audio >= max(1, len(info.get("audio", []))):
        raise HTTPException(400, "Faixa de áudio inválida")
    if burn is not None and (burn >= len(info.get("subtitles", [])) or info["subtitles"][burn]["text"]):
        raise HTTPException(400, "Somente legendas de imagem podem ser embutidas no vídeo")
    body = await service.transcode(item, info, start, audio, burn)
    return StreamingResponse(body, media_type="video/mp4", headers={"Cache-Control": "no-store"})


@app.get("/api/image/{image_id}")
async def get_image(image_id: str, request: Request):
    item = lib(request).item(image_id, "image")
    path = Path(settings.data_dir) / "images" / image_id
    if not path.exists():
        data = await request.app.state.drive.download(image_id, IMAGE_MAX_BYTES)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return FileResponse(
        path,
        media_type=item["mime"] if (item["mime"] or "").startswith("image/") else "image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def api_not_found(path: str):
    raise HTTPException(404, "Rota não encontrada")


# ---------------------------------------------------------------- frontend
static_dir = Path(settings.static_dir)
if (static_dir / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    index = static_dir / "index.html"
    candidate = (static_dir / path).resolve()
    # Arquivos públicos (favicon, manifest...) sem permitir sair do diretório estático
    if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
        return FileResponse(candidate)
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Frontend não compilado"}, status_code=404)
