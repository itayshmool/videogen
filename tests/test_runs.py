"""Tests for run management — directory creation and manifest persistence."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from videogen.config import create_run_dir
from videogen.models import RunManifest, RunStatus


class TestCreateRunDir:
    def test_creates_directory_structure(self, tmp_path):
        with patch("videogen.config.RUNS_DIR", tmp_path / "runs"):
            run_dir = create_run_dir("test_run")

        assert run_dir.exists()
        assert (run_dir / "screenshots").is_dir()
        assert (run_dir / "frames").is_dir()
        assert run_dir.name == "test_run"

    def test_auto_generates_timestamp_id(self, tmp_path):
        with patch("videogen.config.RUNS_DIR", tmp_path / "runs"):
            run_dir = create_run_dir()

        # Should match YYYYMMDD_HHMMSS format
        assert re.match(r"\d{8}_\d{6}", run_dir.name)

    def test_custom_id_used_as_dirname(self, tmp_path):
        with patch("videogen.config.RUNS_DIR", tmp_path / "runs"):
            run_dir = create_run_dir("my_custom_id")

        assert run_dir.name == "my_custom_id"

    def test_idempotent_on_existing_dir(self, tmp_path):
        with patch("videogen.config.RUNS_DIR", tmp_path / "runs"):
            run_dir1 = create_run_dir("same_id")
            run_dir2 = create_run_dir("same_id")

        assert run_dir1 == run_dir2
        assert run_dir1.exists()


class TestRunManifest:
    def test_default_status_is_running(self):
        m = RunManifest(run_id="test", url="https://example.com", created_at="2026-01-01T00:00:00Z")
        assert m.status == RunStatus.RUNNING

    def test_serialization_roundtrip(self):
        m = RunManifest(
            run_id="20260401_003422",
            url="https://example.com",
            created_at="2026-04-01T00:34:22Z",
            status=RunStatus.DONE,
            finished_at="2026-04-01T00:35:00Z",
            product_name="TestProduct",
            hook="Stop wasting time",
            cta="Try it free",
            scenes_count=3,
            config={"width": 1920, "height": 1080, "landscape": True},
        )
        data = json.loads(m.model_dump_json())
        restored = RunManifest(**data)
        assert restored.run_id == m.run_id
        assert restored.status == RunStatus.DONE
        assert restored.product_name == "TestProduct"
        assert restored.config["landscape"] is True

    def test_error_field(self):
        m = RunManifest(
            run_id="err",
            url="https://example.com",
            created_at="2026-01-01T00:00:00Z",
            status=RunStatus.ERROR,
            error="Something went wrong",
        )
        assert m.error == "Something went wrong"

    def test_write_and_read_from_disk(self, tmp_path):
        m = RunManifest(
            run_id="disk_test",
            url="https://example.com",
            created_at="2026-01-01T00:00:00Z",
        )
        path = tmp_path / "run.json"
        path.write_text(m.model_dump_json(indent=2))

        loaded = RunManifest(**json.loads(path.read_text()))
        assert loaded.run_id == "disk_test"
        assert loaded.url == "https://example.com"
