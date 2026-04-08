"""Tests for download integrity — detects truncation, corruption, and network failures.

These tests use mocked HTTP responses to simulate real-world download problems
without hitting external APIs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from mcp_server.civitai_client import CivitAIClient
from mcp_server.huggingface_client import HuggingFaceClient


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_test_data(size: int = 1024 * 1024) -> bytes:
    """Generate deterministic test data of a given size."""
    import random
    rng = random.Random(42)
    return bytes(rng.getrandbits(8) for _ in range(size))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


class FakeStreamReader:
    """Simulates aiohttp response content for iter_chunked."""

    def __init__(self, data: bytes, truncate_at: int = 0):
        self._data = data
        self._truncate_at = truncate_at

    def iter_chunked(self, size: int):
        data = self._data
        if self._truncate_at > 0:
            data = data[:self._truncate_at]
        return _ChunkIterator(data, size)


class _ChunkIterator:
    def __init__(self, data: bytes, chunk_size: int):
        self._data = data
        self._chunk_size = chunk_size
        self._offset = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._offset >= len(self._data):
            raise StopAsyncIteration
        end = min(self._offset + self._chunk_size, len(self._data))
        chunk = self._data[self._offset:end]
        self._offset = end
        return chunk


class FakeResponse:
    """Simulates an aiohttp response with async context manager support."""

    def __init__(self, data: bytes, status: int = 200, content_length: int | None = None,
                 truncate_at: int = 0):
        self.status = status
        self._data = data
        self._content_length = content_length if content_length is not None else len(data)
        self.headers = {"Content-Length": str(self._content_length)}
        self.content = FakeStreamReader(data, truncate_at=truncate_at)

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=self.status,
                message=f"HTTP {self.status}",
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeSession:
    """Fake aiohttp session that returns FakeResponse from get()."""

    def __init__(self, response=None, side_effect=None):
        self._response = response
        self._side_effect = side_effect
        self._call_count = 0
        self.closed = False

    def get(self, url, **kwargs):
        self._call_count += 1
        if self._side_effect:
            result = self._side_effect(url, call_count=self._call_count)
            if isinstance(result, Exception):
                raise result
            return result
        return self._response

    @property
    def call_count(self):
        return self._call_count


def _fake_version_response(sha256: str = "", size_kb: float = 0, filename: str = "model.safetensors"):
    """Create a fake CivitAI version response."""
    return {
        "id": 12345,
        "downloadUrl": "https://civitai.com/api/download/models/12345",
        "files": [{
            "name": filename,
            "sizeKB": size_kb,
            "hashes": {"SHA256": sha256} if sha256 else {},
        }],
    }


# ══════════════════════════════════════════════════════════════════════════
# CivitAI Download Tests
# ══════════════════════════════════════════════════════════════════════════


class TestCivitAIDownloadIntegrity:
    """Test CivitAI download with integrity checks."""

    @pytest.mark.asyncio
    async def test_successful_download(self, tmp_models_dir: Path):
        """A complete download with matching size and hash should succeed."""
        data = _make_test_data(2 * 1024 * 1024)
        sha = _sha256_hex(data)
        size_kb = len(data) / 1024

        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "get_version", return_value=_fake_version_response(sha, size_kb)):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir)

        assert result["status"] == "downloaded"
        assert result["integrity"]["size_match"] is True
        assert result["integrity"]["hash_match"] is True
        assert (tmp_models_dir / "model.safetensors").exists()
        assert (tmp_models_dir / "model.safetensors").stat().st_size == len(data)

    @pytest.mark.asyncio
    async def test_truncated_download_detected(self, tmp_models_dir: Path):
        """A truncated download (Content-Length mismatch) should be detected and file removed."""
        data = _make_test_data(2 * 1024 * 1024)
        truncated_size = 1 * 1024 * 1024

        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(
            data, content_length=len(data), truncate_at=truncated_size,
        ))

        with patch.object(client, "get_version", return_value=_fake_version_response()):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=1)

        assert "error" in result
        assert "truncated" in result["error"].lower()
        assert not (tmp_models_dir / "model.safetensors").exists()

    @pytest.mark.asyncio
    async def test_sha256_mismatch_detected(self, tmp_models_dir: Path):
        """A download with wrong SHA256 should be detected and file removed."""
        data = _make_test_data(1024 * 1024)
        wrong_sha = "A" * 64

        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "get_version", return_value=_fake_version_response(wrong_sha, len(data) / 1024)):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=1)

        assert "error" in result
        assert "SHA256" in result["error"]
        assert not (tmp_models_dir / "model.safetensors").exists()

    @pytest.mark.asyncio
    async def test_size_mismatch_from_metadata(self, tmp_models_dir: Path):
        """A download where actual size differs from CivitAI metadata should be caught."""
        data = _make_test_data(1024 * 1024)
        wrong_size_kb = 5000  # CivitAI says 5MB but only 1MB

        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "get_version", return_value=_fake_version_response("", wrong_size_kb)):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=1)

        assert "error" in result
        assert "mismatch" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, tmp_models_dir: Path):
        """Network errors should trigger retries."""
        data = _make_test_data(1024 * 1024)
        sha = _sha256_hex(data)

        client = CivitAIClient(models_root=tmp_models_dir)

        def side_effect(url, call_count=0):
            if call_count < 3:
                raise aiohttp.ClientError("Connection reset")
            return FakeResponse(data)

        session = FakeSession(side_effect=side_effect)

        with patch.object(client, "get_version", return_value=_fake_version_response(sha, len(data) / 1024)):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=3)

        assert result["status"] == "downloaded"
        assert session.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, tmp_models_dir: Path):
        """When all retries fail, should return error."""
        client = CivitAIClient(models_root=tmp_models_dir)

        def side_effect(url, call_count=0):
            raise aiohttp.ClientError("Connection refused")

        session = FakeSession(side_effect=side_effect)

        with patch.object(client, "get_version", return_value=_fake_version_response()):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=2)

        assert "error" in result
        assert "2 attempts" in result["error"]

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self, tmp_models_dir: Path):
        """401 errors should not be retried — it's a config issue."""
        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(b"", status=401))

        with patch.object(client, "get_version", return_value=_fake_version_response()):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(12345, tmp_models_dir, retries=3)

        assert "error" in result
        assert "Authentication" in result["error"]
        # Should only call once (no retry on auth error)
        assert session.call_count == 1

    @pytest.mark.asyncio
    async def test_progress_callback_called(self, tmp_models_dir: Path):
        """Progress callback should be invoked during download."""
        data = _make_test_data(10 * 1024 * 1024)  # 10MB
        progress_calls = []

        def on_progress(downloaded, total):
            progress_calls.append((downloaded, total))

        client = CivitAIClient(models_root=tmp_models_dir)
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "get_version", return_value=_fake_version_response()):
            with patch.object(client, "_get_session", return_value=session):
                result = await client.download_model(
                    12345, tmp_models_dir, on_progress=on_progress,
                )

        assert result["status"] == "downloaded"
        assert len(progress_calls) >= 1
        assert progress_calls[-1][0] == len(data)

    @pytest.mark.asyncio
    async def test_no_files_in_version(self, tmp_models_dir: Path):
        """Version with no files should return an error."""
        client = CivitAIClient(models_root=tmp_models_dir)

        with patch.object(client, "get_version", return_value={"id": 1, "files": []}):
            result = await client.download_model(1, tmp_models_dir)

        assert result["error"] == "No files found for this version"

    @pytest.mark.asyncio
    async def test_no_download_url(self, tmp_models_dir: Path):
        """Version with no download URL should return an error."""
        client = CivitAIClient(models_root=tmp_models_dir)

        version = {"id": 1, "downloadUrl": "", "files": [{"name": "x.safetensors"}]}
        with patch.object(client, "get_version", return_value=version):
            result = await client.download_model(1, tmp_models_dir)

        assert result["error"] == "No download URL available"


# ══════════════════════════════════════════════════════════════════════════
# HuggingFace Download Tests
# ══════════════════════════════════════════════════════════════════════════


class TestHuggingFaceDownloadIntegrity:
    """Test HuggingFace download with integrity checks."""

    @pytest.mark.asyncio
    async def test_successful_download(self, tmp_models_dir: Path):
        """A complete download should succeed and report size_match."""
        data = _make_test_data(2 * 1024 * 1024)
        client = HuggingFaceClient()
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "_get_session", return_value=session):
            result = await client.download_file(
                "https://huggingface.co/repo/resolve/main/model.safetensors",
                tmp_models_dir,
            )

        assert result["status"] == "downloaded"
        assert result["integrity"]["size_match"] is True
        assert (tmp_models_dir / "model.safetensors").exists()

    @pytest.mark.asyncio
    async def test_truncated_download_detected(self, tmp_models_dir: Path):
        """Truncated HuggingFace download should be detected."""
        data = _make_test_data(2 * 1024 * 1024)
        truncated = 1 * 1024 * 1024

        client = HuggingFaceClient()
        session = FakeSession(response=FakeResponse(
            data, content_length=len(data), truncate_at=truncated,
        ))

        with patch.object(client, "_get_session", return_value=session):
            result = await client.download_file(
                "https://huggingface.co/repo/resolve/main/model.safetensors",
                tmp_models_dir,
                retries=1,
            )

        assert "error" in result
        assert "truncated" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, tmp_models_dir: Path):
        """Network errors should trigger retries for HuggingFace."""
        data = _make_test_data(1024 * 1024)
        client = HuggingFaceClient()

        def side_effect(url, call_count=0):
            if call_count < 2:
                raise aiohttp.ClientError("Timeout")
            return FakeResponse(data)

        session = FakeSession(side_effect=side_effect)

        with patch.object(client, "_get_session", return_value=session):
            result = await client.download_file(
                "https://huggingface.co/repo/resolve/main/model.safetensors",
                tmp_models_dir,
                retries=3,
            )

        assert result["status"] == "downloaded"
        assert session.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, tmp_models_dir: Path):
        """When all retries fail, should return error."""
        client = HuggingFaceClient()

        def side_effect(url, call_count=0):
            raise aiohttp.ClientError("Network unreachable")

        session = FakeSession(side_effect=side_effect)

        with patch.object(client, "_get_session", return_value=session):
            result = await client.download_file(
                "https://huggingface.co/repo/resolve/main/model.safetensors",
                tmp_models_dir,
                retries=2,
            )

        assert "error" in result
        assert "2 attempts" in result["error"]

    @pytest.mark.asyncio
    async def test_filename_from_url(self, tmp_models_dir: Path):
        """Filename should be extracted from URL when not provided."""
        data = _make_test_data(1024)
        client = HuggingFaceClient()
        session = FakeSession(response=FakeResponse(data))

        with patch.object(client, "_get_session", return_value=session):
            result = await client.download_file(
                "https://huggingface.co/repo/resolve/main/my_model.safetensors",
                tmp_models_dir,
            )

        assert result["filename"] == "my_model.safetensors"
        assert (tmp_models_dir / "my_model.safetensors").exists()


# ══════════════════════════════════════════════════════════════════════════
# CivitAI Client Unit Tests
# ══════════════════════════════════════════════════════════════════════════


class TestCivitAIClient:
    """Unit tests for CivitAI client methods."""

    def test_resolve_target_dir_known_types(self, tmp_models_dir: Path):
        """Known model types should resolve to correct subdirectories."""
        client = CivitAIClient(models_root=tmp_models_dir)
        assert client.resolve_target_dir("Checkpoint") == tmp_models_dir / "checkpoints"
        assert client.resolve_target_dir("LORA") == tmp_models_dir / "loras"
        assert client.resolve_target_dir("VAE") == tmp_models_dir / "vae"
        assert client.resolve_target_dir("Controlnet") == tmp_models_dir / "controlnet"
        assert client.resolve_target_dir("Upscaler") == tmp_models_dir / "upscale_models"

    def test_resolve_target_dir_unknown_type(self, tmp_models_dir: Path):
        """Unknown model types should pass through as-is."""
        client = CivitAIClient(models_root=tmp_models_dir)
        assert client.resolve_target_dir("CustomType") == tmp_models_dir / "CustomType"

    def test_nsfw_filter_levels(self):
        """Filter should exclude correct ratings per level."""
        client_none = CivitAIClient(nsfw_filter="none")
        assert client_none._should_exclude("Soft") is True
        assert client_none._should_exclude("X") is True

        client_soft = CivitAIClient(nsfw_filter="soft")
        assert client_soft._should_exclude("Soft") is False
        assert client_soft._should_exclude("Mature") is True

        client_x = CivitAIClient(nsfw_filter="x")
        assert client_x._should_exclude("X") is False
        assert client_x._should_exclude("Mature") is False
