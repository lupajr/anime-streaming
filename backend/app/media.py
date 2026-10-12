"""FFmpeg: análise (ffprobe), transcodificação sob demanda e extração de legendas."""
import asyncio
import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import AsyncIterator

from .config import Settings
from .db import DB
from .drive import DriveClient

log = logging.getLogger("media")

TEXT_SUB_CODECS = {"ass", "ssa", "subrip", "srt", "webvtt", "mov_text", "text"}
COPYABLE_PIX_FMTS = {"yuv420p", "yuvj420p"}
PROBE_TIMEOUT = 90
SUB_TIMEOUT = 45 * 60


class MediaError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _tags(stream: dict) -> dict:
    return {k.lower(): v for k, v in (stream.get("tags") or {}).items()}


def _parse_probe(raw: dict) -> dict:
    streams = raw.get("streams", [])
    fmt = raw.get("format", {})

    video = next(
        (s for s in streams if s.get("codec_type") == "video"
         and not (s.get("disposition") or {}).get("attached_pic")),
        None,
    )
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]

    def audio_info(i: int, s: dict) -> dict:
        t = _tags(s)
        return {
            "index": i,
            "codec": s.get("codec_name"),
            "channels": s.get("channels"),
            "language": t.get("language"),
            "title": t.get("title"),
            "default": bool((s.get("disposition") or {}).get("default")),
        }

    def sub_info(i: int, s: dict) -> dict:
        t = _tags(s)
        return {
            "index": i,
            "codec": s.get("codec_name"),
            "language": t.get("language"),
            "title": t.get("title"),
            "default": bool((s.get("disposition") or {}).get("default")),
            "forced": bool((s.get("disposition") or {}).get("forced")),
            "text": s.get("codec_name") in TEXT_SUB_CODECS,
        }

    audio_list = [audio_info(i, s) for i, s in enumerate(audios)]
    default_audio = next((a["index"] for a in audio_list if a["default"]), 0)

    vinfo = None
    if video:
        vinfo = {
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "pix_fmt": video.get("pix_fmt"),
            "width": video.get("width"),
            "height": video.get("height"),
        }
        vinfo["copy_ok"] = (
            vinfo["codec"] == "h264"
            and vinfo["pix_fmt"] in COPYABLE_PIX_FMTS
            and "10" not in (vinfo["profile"] or "")
        )

    chapters = []
    for c in raw.get("chapters", []) or []:
        try:
            chapters.append({
                "start": float(c.get("start_time", 0)),
                "end": float(c.get("end_time", 0)),
                "title": _tags(c).get("title", ""),
            })
        except (TypeError, ValueError):
            continue

    return {
        "duration": float(fmt.get("duration") or 0),
        "container": fmt.get("format_name"),
        "video": vinfo,
        "audio": audio_list,
        "default_audio": default_audio,
        "subtitles": [sub_info(i, s) for i, s in enumerate(subs)],
        "chapters": chapters,
    }


class MediaService:
    def __init__(self, drive: DriveClient, db: DB, settings: Settings):
        self.drive = drive
        self.db = db
        self.settings = settings
        self.subs_dir = Path(settings.data_dir) / "subs"
        self.subs_dir.mkdir(parents=True, exist_ok=True)
        self._transcode_sem = asyncio.Semaphore(settings.max_transcodes)
        self._sub_sem = asyncio.Semaphore(settings.max_subtitle_jobs)
        self._sub_jobs: dict[str, asyncio.Task] = {}
        self._probe_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._active_transcodes = 0
        self._background: set[asyncio.Task] = set()

    def _auth_header(self, token: str) -> str:
        return f"Authorization: Bearer {token}\r\n"

    def _http_input_args(self, token: str) -> list[str]:
        return [
            "-headers", self._auth_header(token),
            "-reconnect", "1",
            "-reconnect_on_network_error", "1",
            "-reconnect_delay_max", "10",
        ]

    async def _run(self, args: list[str], timeout: float) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            proc.kill()
            await proc.wait()
            raise
        return proc.returncode, out, err

    # ----------------------------------------------------------------- probe
    async def probe(self, item) -> dict:
        cached = self.db.one("SELECT modified, data FROM probe WHERE id = ?", (item["id"],))
        if cached and cached["modified"] == item["modified"]:
            return json.loads(cached["data"])

        async with self._probe_locks[item["id"]]:
            cached = self.db.one("SELECT modified, data FROM probe WHERE id = ?", (item["id"],))
            if cached and cached["modified"] == item["modified"]:
                return json.loads(cached["data"])

            token = await self.drive.token()
            self.drive.count_ffmpeg("ffprobe")
            args = [
                "ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", "-show_chapters",
                *self._http_input_args(token), self.drive.media_url(item["id"]),
            ]
            try:
                code, out, err = await self._run(args, PROBE_TIMEOUT)
            except asyncio.TimeoutError as exc:
                raise MediaError("Tempo esgotado ao analisar o vídeo", 504) from exc
            if code != 0:
                log.warning("ffprobe falhou (%s): %s", item["id"], err.decode(errors="replace")[:500])
                raise MediaError("Não foi possível analisar o vídeo")
            info = _parse_probe(json.loads(out or b"{}"))
            self.db.execute(
                "INSERT OR REPLACE INTO probe (id, modified, data) VALUES (?, ?, ?)",
                (item["id"], item["modified"], json.dumps(info)),
            )
            return info

    async def keyframe_before(self, item, t: float) -> float:
        """Posição do keyframe usado ao buscar `t` (necessário para copiar vídeo sem dessincronizar)."""
        if t <= 0:
            return 0.0
        token = await self.drive.token()
        self.drive.count_ffmpeg("keyframe")
        args = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-read_intervals", f"{t:.3f}%+#8",
            "-show_entries", "packet=pts_time,flags", "-of", "json",
            *self._http_input_args(token), self.drive.media_url(item["id"]),
        ]
        try:
            code, out, _ = await self._run(args, 30)
            if code == 0:
                for p in json.loads(out or b"{}").get("packets", []):
                    if "K" in (p.get("flags") or "") and p.get("pts_time") is not None:
                        return max(0.0, float(p["pts_time"]))
        except (asyncio.TimeoutError, ValueError):
            pass
        return t

    # ------------------------------------------------------------- transcode
    async def transcode(
        self, item, info: dict, start: float, audio: int, burn: int | None
    ) -> AsyncIterator[bytes]:
        if self._transcode_sem.locked():
            raise MediaError("Limite de transcodificações simultâneas atingido", 503)
        await self._transcode_sem.acquire()
        try:
            token = await self.drive.token(min_valid=2400)
            video = info.get("video") or {}
            copy_video = bool(video.get("copy_ok")) and burn is None
            max_h = self.settings.transcode_max_height
            scale = f"scale=-2:'min({max_h},ih)'"

            args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                    *self._http_input_args(token)]
            if start > 0:
                args += ["-ss", f"{start:.3f}"]
            args += ["-i", self.drive.media_url(item["id"])]

            if burn is not None:
                args += ["-filter_complex",
                         f"[0:v:0][0:s:{burn}]overlay=eof_action=pass,{scale},format=yuv420p[v]",
                         "-map", "[v]"]
            else:
                args += ["-map", "0:v:0"]
            args += ["-map", f"0:a:{audio}?"]

            if copy_video:
                args += ["-c:v", "copy"]
            else:
                args += ["-c:v", "libx264", "-preset", self.settings.transcode_preset,
                         "-crf", str(self.settings.transcode_crf), "-tune", "animation",
                         "-profile:v", "high", "-pix_fmt", "yuv420p"]
                if burn is None:
                    args += ["-vf", scale]

            args += [
                "-c:a", "aac", "-ac", "2", "-b:a", "192k",
                "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
                "-max_muxing_queue_size", "1024",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "-frag_duration", "2000000",
                "-f", "mp4", "pipe:1",
            ]

            self.drive.count_ffmpeg("transcode")
            proc = await asyncio.create_subprocess_exec(
                *args, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except BaseException:
            self._transcode_sem.release()
            raise

        self._active_transcodes += 1
        log.info("Transcodificando %s (início=%.1fs, cópia de vídeo=%s, áudio=%d, burn=%s)",
                 item["id"], start, copy_video, audio, burn)
        stderr_task = asyncio.create_task(self._drain_stderr(proc, item["id"]))
        self._track(stderr_task)

        async def body() -> AsyncIterator[bytes]:
            try:
                while True:
                    chunk = await proc.stdout.read(256 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
                self._track(asyncio.create_task(proc.wait()))
                self._active_transcodes -= 1
                self._transcode_sem.release()

        return body()

    async def _drain_stderr(self, proc, file_id: str) -> None:
        assert proc.stderr is not None
        async for line in proc.stderr:
            text = line.decode(errors="replace").strip()
            if text:
                log.warning("ffmpeg[%s]: %s", file_id, text[:300])

    def _track(self, task: asyncio.Task) -> None:
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------- subtitles
    def _sub_path(self, file_id: str, index: int, partial: bool = False) -> Path:
        return self.subs_dir / f"{file_id}.{index}.vtt{'.part' if partial else ''}"

    def subtitle(self, item, info: dict, index: int) -> tuple[str, bool]:
        subs = info.get("subtitles", [])
        if index < 0 or index >= len(subs) or not subs[index]["text"]:
            raise MediaError("Legenda indisponível", 404)

        final = self._sub_path(item["id"], index)
        if final.exists():
            return final.read_text(encoding="utf-8", errors="replace"), True

        job = self._sub_jobs.get(item["id"])
        if job is None or job.done():
            job = asyncio.create_task(self._extract_subs(item, info))
            self._sub_jobs[item["id"]] = job

        part = self._sub_path(item["id"], index, partial=True)
        text = part.read_text(encoding="utf-8", errors="replace") if part.exists() else "WEBVTT\n\n"
        return text, False

    async def _extract_subs(self, item, info: dict) -> None:
        """Extrai TODAS as legendas de texto numa única leitura do arquivo (1 download)."""
        text_subs = [s for s in info.get("subtitles", []) if s["text"]]
        file_id = item["id"]
        try:
            async with self._sub_sem:
                token = await self.drive.token(min_valid=2400)
                args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
                        *self._http_input_args(token), "-i", self.drive.media_url(file_id)]
                for s in text_subs:
                    args += ["-map", f"0:s:{s['index']}", "-c:s", "webvtt",
                             "-flush_packets", "1", "-f", "webvtt",
                             str(self._sub_path(file_id, s["index"], partial=True))]
                self.drive.count_ffmpeg("subtitles")
                started = time.monotonic()
                code, _, err = await self._run(args, SUB_TIMEOUT)
                if code == 0:
                    for s in text_subs:
                        part = self._sub_path(file_id, s["index"], partial=True)
                        if part.exists():
                            part.replace(self._sub_path(file_id, s["index"]))
                    log.info("Legendas extraídas de %s em %.0fs", file_id, time.monotonic() - started)
                else:
                    log.warning("Extração de legendas falhou (%s): %s", file_id,
                                err.decode(errors="replace")[:500])
                    self._cleanup_parts(file_id, text_subs)
        except Exception:  # noqa: BLE001
            log.exception("Erro extraindo legendas de %s", file_id)
            self._cleanup_parts(file_id, text_subs)
        finally:
            self._sub_jobs.pop(file_id, None)

    def _cleanup_parts(self, file_id: str, subs: list[dict]) -> None:
        for s in subs:
            self._sub_path(file_id, s["index"], partial=True).unlink(missing_ok=True)

    def stats(self) -> dict:
        return {
            "active_transcodes": self._active_transcodes,
            "subtitle_jobs": len(self._sub_jobs),
        }

    async def shutdown(self) -> None:
        for job in list(self._sub_jobs.values()):
            job.cancel()
