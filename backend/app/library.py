"""Biblioteca de animes: sincroniza a árvore do Drive e monta as visões de pastas/episódios."""
import asyncio
import logging
import re
import time
from collections import defaultdict
from pathlib import PurePosixPath

from .config import Settings
from .db import DB
from .drive import FOLDER_MIME, DriveClient, DriveError, valid_id

log = logging.getLogger("library")

VIDEO_EXT = {".mkv", ".mp4", ".m4v", ".webm", ".avi", ".mov", ".ts"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
COVER_STEMS = ("cover", "poster", "folder", "capa", "thumb")
WATCHED_RATIO = 0.90
_NUM_RE = re.compile(r"(\d+)")


class LibraryError(Exception):
    def __init__(self, message: str, status: int = 503):
        super().__init__(message)
        self.status = status


def classify(f: dict) -> str | None:
    mime = f.get("mimeType", "")
    ext = PurePosixPath(f.get("name", "")).suffix.lower()
    if mime == FOLDER_MIME:
        return "folder"
    if ext in VIDEO_EXT or mime.startswith("video/"):
        return "video"
    if ext in IMAGE_EXT and mime.startswith("image/"):
        return "image"
    return None


def natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.casefold() for t in _NUM_RE.split(name)]


def title_of(name: str, kind: str) -> str:
    return PurePosixPath(name).stem if kind == "video" else name


def _progress_dict(row) -> dict | None:
    if not row:
        return None
    duration = row["duration"] or 0
    return {
        "position": row["position"],
        "duration": duration,
        "watched": bool(duration) and row["position"] >= duration * WATCHED_RATIO,
        "updated_at": row["updated_at"],
    }


class Library:
    def __init__(self, db: DB, drive: DriveClient, settings: Settings):
        self.db = db
        self.drive = drive
        self.settings = settings
        self._sync_lock = asyncio.Lock()
        self._generation = 0
        self._last_forced = 0.0
        self._bg_task: asyncio.Task | None = None

    # ------------------------------------------------------------------ sync
    async def _resolve_root(self) -> tuple[str, str | None]:
        if self.settings.drive_folder_id:
            if not valid_id(self.settings.drive_folder_id):
                raise LibraryError("DRIVE_FOLDER_ID inválido no .env")
            return self.settings.drive_folder_id, None
        cached = self.db.kv_get("root_id")
        if cached:
            return cached, self.db.kv_get("root_name")
        folder = await self.drive.find_folder(self.settings.drive_folder_name)
        if not folder:
            email = self.drive.service_account_email or "(service account)"
            raise LibraryError(
                f"Pasta '{self.settings.drive_folder_name}' não encontrada. "
                f"Compartilhe-a no Google Drive com {email} (permissão Leitor)."
            )
        self.db.kv_set("root_id", folder["id"])
        self.db.kv_set("root_name", folder["name"])
        return folder["id"], folder["name"]

    async def _sync(self) -> None:
        started = time.monotonic()
        root_id, root_name = await self._resolve_root()
        files = await self.drive.list_all()

        by_parent: dict[str, list[tuple[dict, str]]] = defaultdict(list)
        for f in files:
            if f["id"] == root_id:
                root_name = f.get("name", root_name)
            kind = classify(f)
            if not kind:
                continue
            for parent in f.get("parents", []) or []:
                by_parent[parent].append((f, kind))

        rows: list[tuple] = []
        seen = {root_id}
        stack = [root_id]
        while stack:
            parent = stack.pop()
            for f, kind in by_parent.get(parent, []):
                if f["id"] in seen:
                    continue
                seen.add(f["id"])
                rows.append(
                    (f["id"], parent, f["name"], f.get("mimeType"),
                     int(f.get("size") or 0), f.get("modifiedTime", ""), kind)
                )
                if kind == "folder":
                    stack.append(f["id"])

        self.db.replace_items(rows)
        self.db.kv_set("root_id", root_id)
        self.db.kv_set("root_name", root_name or self.settings.drive_folder_name)
        self.db.kv_set("last_sync", str(time.time()))
        self._generation += 1
        log.info(
            "Biblioteca sincronizada: %d itens (de %d visíveis) em %.1fs",
            len(rows), len(files), time.monotonic() - started,
        )

    async def _sync_once(self, generation: int) -> None:
        async with self._sync_lock:
            if self._generation != generation:
                return  # outra requisição acabou de sincronizar
            await self._sync()

    async def _background_sync(self, generation: int) -> None:
        try:
            await self._sync_once(generation)
        except Exception:  # noqa: BLE001
            log.exception("Falha na sincronização em segundo plano")

    async def ensure_fresh(self) -> None:
        """Stale-while-revalidate: só bloqueia na primeira sincronização."""
        last = float(self.db.kv_get("last_sync") or 0)
        generation = self._generation
        if not last:
            try:
                await self._sync_once(generation)
            except DriveError as exc:
                raise LibraryError(str(exc)) from exc
        elif time.time() - last > self.settings.library_ttl_seconds:
            if not self._bg_task or self._bg_task.done():
                self._bg_task = asyncio.create_task(self._background_sync(generation))

    async def refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_forced < 30:
            raise LibraryError("Aguarde alguns segundos antes de atualizar novamente.", 429)
        self._last_forced = now
        try:
            await self._sync_once(self._generation)
        except DriveError as exc:
            raise LibraryError(str(exc)) from exc

    # ----------------------------------------------------------------- views
    def root_id(self) -> str:
        rid = self.db.kv_get("root_id")
        if not rid:
            raise LibraryError("Biblioteca ainda não sincronizada")
        return rid

    def item(self, item_id: str, kind: str | None = None):
        if not valid_id(item_id):
            raise LibraryError("ID inválido", 400)
        row = self.db.one("SELECT * FROM items WHERE id = ?", (item_id,))
        if not row or (kind and row["kind"] != kind):
            raise LibraryError("Item não encontrado na biblioteca", 404)
        return row

    def _breadcrumb(self, folder_id: str) -> list[dict]:
        root = self.root_id()
        crumbs: list[dict] = []
        current = folder_id
        for _ in range(32):
            if current == root:
                break
            row = self.db.one("SELECT id, parent_id, name FROM items WHERE id = ?", (current,))
            if not row:
                break
            crumbs.append({"id": row["id"], "name": row["name"]})
            current = row["parent_id"]
        crumbs.append({"id": "root", "name": self.db.kv_get("root_name") or "Animes"})
        return list(reversed(crumbs))

    def _covers(self, folder_ids: list[str]) -> dict[str, str]:
        if not folder_ids:
            return {}
        marks = ",".join("?" * len(folder_ids))
        rows = self.db.query(
            f"SELECT id, parent_id, name FROM items WHERE kind = 'image' AND parent_id IN ({marks})",
            folder_ids,
        )
        best: dict[str, tuple[int, str]] = {}
        for r in rows:
            stem = PurePosixPath(r["name"]).stem.casefold()
            score = 0 if stem in COVER_STEMS else 1
            if r["parent_id"] not in best or score < best[r["parent_id"]][0]:
                best[r["parent_id"]] = (score, r["id"])
        return {k: v[1] for k, v in best.items()}

    def _progress_map(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.db.query(f"SELECT * FROM progress WHERE id IN ({marks})", ids)
        return {r["id"]: _progress_dict(r) for r in rows}

    def _video_dict(self, row, progress: dict | None) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "title": title_of(row["name"], "video"),
            "size": row["size"],
            "progress": progress,
        }

    def _sorted_videos(self, folder_id: str):
        rows = self.db.query(
            "SELECT * FROM items WHERE parent_id = ? AND kind = 'video'", (folder_id,)
        )
        return sorted(rows, key=lambda r: natural_key(r["name"]))

    def folder_view(self, folder_id: str) -> dict:
        root = self.root_id()
        if folder_id in ("root", root):
            fid, name, parent = root, self.db.kv_get("root_name") or "Animes", None
        else:
            row = self.item(folder_id, "folder")
            fid, name = row["id"], row["name"]
            parent = "root" if row["parent_id"] == root else row["parent_id"]

        children = self.db.query("SELECT * FROM items WHERE parent_id = ?", (fid,))
        folders = sorted((c for c in children if c["kind"] == "folder"), key=lambda r: natural_key(r["name"]))
        videos = sorted((c for c in children if c["kind"] == "video"), key=lambda r: natural_key(r["name"]))

        folder_ids = [f["id"] for f in folders]
        covers = self._covers(folder_ids + [fid])
        counts: dict[str, int] = {}
        if folder_ids:
            marks = ",".join("?" * len(folder_ids))
            for r in self.db.query(
                f"SELECT parent_id, COUNT(*) AS n FROM items WHERE kind IN ('video','folder')"
                f" AND parent_id IN ({marks}) GROUP BY parent_id",
                folder_ids,
            ):
                counts[r["parent_id"]] = r["n"]

        progress = self._progress_map([v["id"] for v in videos])
        return {
            "id": "root" if fid == root else fid,
            "name": name,
            "parent": parent,
            "cover": covers.get(fid),
            "breadcrumb": self._breadcrumb(fid),
            "folders": [
                {"id": f["id"], "name": f["name"], "cover": covers.get(f["id"]), "count": counts.get(f["id"], 0)}
                for f in folders
            ],
            "videos": [self._video_dict(v, progress.get(v["id"])) for v in videos],
            "last_sync": float(self.db.kv_get("last_sync") or 0),
        }

    def file_view(self, file_id: str) -> dict:
        row = self.item(file_id, "video")
        siblings = self._sorted_videos(row["parent_id"])
        ids = [s["id"] for s in siblings]
        idx = ids.index(row["id"])
        prog = self._progress_map([row["id"]]).get(row["id"])
        root = self.root_id()
        parent_name = (
            self.db.kv_get("root_name") if row["parent_id"] == root
            else (self.db.one("SELECT name FROM items WHERE id = ?", (row["parent_id"],)) or {"name": ""})["name"]
        )
        return {
            **self._video_dict(row, prog),
            "parent": "root" if row["parent_id"] == root else row["parent_id"],
            "parent_name": parent_name,
            "breadcrumb": self._breadcrumb(row["parent_id"]),
            "index": idx + 1,
            "total": len(ids),
            "prev": self._video_dict(siblings[idx - 1], None) if idx > 0 else None,
            "next": self._video_dict(siblings[idx + 1], None) if idx + 1 < len(ids) else None,
        }

    def continue_watching(self, limit: int = 12) -> list[dict]:
        """Último episódio por pasta; se já foi assistido, sugere o próximo."""
        rows = self.db.query(
            "SELECT p.*, i.parent_id, i.name FROM progress p JOIN items i ON i.id = p.id"
            " ORDER BY p.updated_at DESC LIMIT 200"
        )
        root = self.root_id()
        seen_parents: set[str] = set()
        result: list[dict] = []
        for r in rows:
            if r["parent_id"] in seen_parents:
                continue
            seen_parents.add(r["parent_id"])
            prog = _progress_dict(r)
            target, target_prog = r, prog
            if prog["watched"]:
                siblings = self._sorted_videos(r["parent_id"])
                ids = [s["id"] for s in siblings]
                idx = ids.index(r["id"]) if r["id"] in ids else -1
                if idx < 0 or idx + 1 >= len(ids):
                    continue  # temporada concluída
                target = siblings[idx + 1]
                target_prog = self._progress_map([target["id"]]).get(target["id"])
            folder = self.db.one("SELECT name, parent_id FROM items WHERE id = ?", (r["parent_id"],))
            cover = self._covers([r["parent_id"]]).get(r["parent_id"])
            if not cover and folder and folder["parent_id"] != root:
                cover = self._covers([folder["parent_id"]]).get(folder["parent_id"])
            result.append({
                **self._video_dict(target, target_prog),
                "folder_id": "root" if r["parent_id"] == root else r["parent_id"],
                "folder_name": folder["name"] if folder else self.db.kv_get("root_name"),
                "cover": cover,
            })
            if len(result) >= limit:
                break
        return result

    def save_progress(self, file_id: str, position: float, duration: float) -> None:
        self.item(file_id, "video")
        self.db.execute(
            "INSERT OR REPLACE INTO progress (id, position, duration, updated_at) VALUES (?, ?, ?, ?)",
            (file_id, position, duration, time.time()),
        )

    def clear_progress(self, file_id: str) -> None:
        self.item(file_id, "video")
        self.db.execute("DELETE FROM progress WHERE id = ?", (file_id,))
