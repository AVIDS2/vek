"""Tests for Phase 6: export / import."""

import os
import tempfile

import vek
from vek import api


class TestExportImport:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = os.getcwd()
        os.chdir(self._tmp)
        vek.init()

    def teardown_method(self):
        os.chdir(self._orig)

    def test_export_json_structure(self):
        vek.store(tool="a", input="1", output="r1")
        data = vek.export()
        assert "version" in data
        assert data["version"] == 1
        assert len(data["nodes"]) == 1
        assert len(data["objects"]) == 2  # input + output
        assert len(data["refs"]) == 1

    def test_export_import_roundtrip(self):
        h1 = vek.store(tool="a", input="1", output="r1")
        h2 = vek.store(tool="b", input="2", output="r2")
        data = vek.export()

        # Create a fresh repo and import
        tmp2 = tempfile.mkdtemp()
        os.chdir(tmp2)
        vek.init()

        stats = vek.import_data(data)
        assert stats["nodes_imported"] == 2
        assert stats["objects_imported"] >= 2
        assert stats["refs_imported"] == 1

    def test_export_jsonl_format(self):
        vek.store(tool="a", input="1", output="r1")
        text = vek.export(format="jsonl")
        assert isinstance(text, str)
        lines = [l for l in text.strip().split("\n") if l]
        assert len(lines) >= 3  # ref + node + objects

    def test_import_jsonl_roundtrip(self):
        vek.store(tool="a", input="i", output="o")
        text = vek.export(format="jsonl")

        tmp2 = tempfile.mkdtemp()
        os.chdir(tmp2)
        vek.init()

        stats = vek.import_data(text, format="jsonl")
        assert stats["nodes_imported"] == 1

    def test_import_skips_duplicates(self):
        vek.store(tool="a", input="1", output="r1")
        data = vek.export()

        # Import into same repo — should skip all
        stats = vek.import_data(data)
        assert stats["nodes_imported"] == 0
        assert stats["objects_imported"] == 0
        assert stats["refs_imported"] == 0

    def test_export_specific_branch(self):
        vek.store(tool="a", input="1", output="r1")
        vek.branch("dev")
        vek.store(tool="b", input="2", output="r2")

        data = vek.export(branch="dev")
        assert len(data["refs"]) == 1
        assert data["refs"][0]["name"] == "dev"
