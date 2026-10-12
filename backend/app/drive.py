"""Cliente mínimo e assíncrono da Google Drive API v3 (somente leitura).

Toda chamada à API passa por `_count()`, permitindo acompanhar o consumo de cota
em /api/stats.
"""
import asyncio
import logging
import re
from collections import Counter
from datetime import datetime, timezone

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

log = logging.getLogger("drive")

API = "https://www.googleapis.com/drive/v3"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,128}$")


class DriveError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def valid_id(value: str) -> bool:
    return bool(ID_RE.fullmatch(value or ""))


def _escape_q(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class DriveClient:
    def __init__(self, credentials_file: str):
        self._credentials_file = credentials_file
        self._creds: service_account.Credentials | None = None
        self._token_lock = asyncio.Lock()
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, read=120.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
        )
        self.calls: Counter[str] = Counter()

    @property
    def service_account_email(self) -> str | None:
        try:
            return self._load_creds().service_account_email
        except Exception:  # noqa: BLE001
            return None

    def _load_creds(self) -> service_account.Credentials:
        if self._creds is None:
            self._creds = service_account.Credentials.from_service_account_file(
                self._credentials_file, scopes=SCOPES
            )
        return self._creds

    def _count(self, kind: str) -> None:
        self.calls[kind] += 1
        log.debug("Drive API call: %s (total=%d)", kind, sum(self.calls.values()))

    async def token(self, min_valid: int = 300) -> str:
        """Retorna um access token válido por pelo menos `min_valid` segundos."""
        async with self._token_lock:
            creds = self._load_creds()
            expiry = creds.expiry  # datetime UTC "naive"
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if not creds.token or expiry is None or (expiry - now).total_seconds() < min_valid:
                await asyncio.to_thread(creds.refresh, GoogleAuthRequest())
            return creds.token

    async def _get_json(self, path: str, params: dict, kind: str) -> dict:
        for attempt in range(3):
            token = await self.token()
            self._count(kind)
            resp = await self.client.get(
                f"{API}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            log.warning("Drive API %s -> %s: %s", path, resp.status_code, resp.text[:300])
            raise DriveError(f"Google Drive respondeu {resp.status_code}", resp.status_code)
        raise DriveError("Google Drive indisponível")

    async def find_folder(self, name: str) -> dict | None:
        data = await self._get_json(
            "/files",
            {
                "q": f"name = '{_escape_q(name)}' and mimeType = '{FOLDER_MIME}' and trashed = false",
                "fields": "files(id,name)",
                "pageSize": "10",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
            "find_folder",
        )
        files = data.get("files", [])
        return files[0] if files else None

    async def list_all(self) -> list[dict]:
        """Lista TUDO que a service account enxerga em poucas chamadas (1000 itens/página).

        Muito mais econômico do que listar pasta por pasta: a árvore é montada localmente.
        """
        files: list[dict] = []
        page_token: str | None = None
        while True:
            params = {
                "q": "trashed = false",
                "fields": "nextPageToken, files(id,name,mimeType,size,modifiedTime,parents)",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._get_json("/files", params, "list")
            files.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return files

    def media_url(self, file_id: str) -> str:
        return f"{API}/files/{file_id}?alt=media&supportsAllDrives=true"

    async def open_media(self, file_id: str, range_header: str | None) -> httpx.Response:
        """Abre o conteúdo do arquivo em streaming, repassando o cabeçalho Range."""
        token = await self.token()
        headers = {"Authorization": f"Bearer {token}"}
        if range_header:
            headers["Range"] = range_header
        self._count("media")
        request = self.client.build_request("GET", self.media_url(file_id), headers=headers)
        return await self.client.send(request, stream=True)

    async def download(self, file_id: str, max_bytes: int) -> bytes:
        resp = await self.open_media(file_id, None)
        try:
            if resp.status_code != 200:
                raise DriveError(f"Google Drive respondeu {resp.status_code}", resp.status_code)
            chunks, total = [], 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise DriveError("Arquivo grande demais", 413)
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            await resp.aclose()

    def count_ffmpeg(self, kind: str) -> None:
        """FFmpeg acessa o Drive diretamente; contabiliza ao menos 1 chamada por execução."""
        self._count(kind)

    async def aclose(self) -> None:
        await self.client.aclose()
