import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import prepare_release
import verify_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        (self.pack / "mods").mkdir(parents=True)
        (self.pack / "pack.toml").write_text(
            'name = "Test Pack"\nversion = "3.0.0-beta"\n'
            '[versions]\nminecraft = "26.3"\nfabric = "0.19.5"\n',
            encoding="utf-8",
        )
        (self.pack / "mods/test.pw.toml").write_text(
            'name = "Test"\nfilename = "test.jar"\n', encoding="utf-8"
        )
        self.cf = self.root / "cf"
        self.cf.mkdir()
        (self.cf / "test.pw.toml").write_text(
            'filename = "test.jar"\n[download]\nmode = "metadata:curseforge"\n'
            '[update.curseforge]\nproject-id = 1\nfile-id = 2\n',
            encoding="utf-8",
        )
        self.changelog = self.root / "CHANGELOG.md"
        self.changelog.write_text(
            "# (3.x.x)\n\n## 26.3\n\n### 3.0.0-beta\n\n2026-10-09\n\n"
            "* Minecraft has been updated to 26.3.\n\n"
            "# (2.x.x)\n\n## 26.2\n\n### 2.2.0\n\n2026-10-05\n\n* Old.\n",
            encoding="utf-8",
        )
        self.notes = self.root / "notes.md"
        self.index = {
            "versionId": "3.0.0-beta",
            "dependencies": {"minecraft": "26.3", "fabric-loader": "0.19.5"},
            "files": [{"path": "mods/test.jar"}],
        }
        self.manifest = {
            "version": "3.0.0-beta",
            "minecraft": {
                "version": "26.3",
                "modLoaders": [{"id": "fabric-0.19.5", "primary": True}],
            },
            "files": [{"projectID": 1, "fileID": 2, "required": True}],
        }
        self.mrpack = self.root / "pack.mrpack"
        self.cf_zip = self.root / "pack.zip"
        self.archives()

    def archives(self, mr_extra=None, cf_extra=None):
        for file, name, data, extras in (
            (self.mrpack, "modrinth.index.json", self.index, mr_extra),
            (self.cf_zip, "manifest.json", self.manifest, cf_extra),
        ):
            with zipfile.ZipFile(file, "w") as archive:
                archive.writestr(name, json.dumps(data))
                archive.writestr("overrides/config/test.json", "{}")
                for path, content in (extras or {}).items():
                    archive.writestr(path, content)

    def prepare(self, *extra):
        args = [
            "prepare", "--pack-dir", str(self.pack),
            "--changelog-file", str(self.changelog), "--release-notes", str(self.notes),
            "--version", "3.0.0", "--stage", "beta", "--minecraft-version", "26.3",
            "--pack-name", "Test Pack", "--display-name", "Test",
            "--artifact-prefix", "test", *extra,
        ]
        with patch("sys.argv", args), patch.dict("os.environ", {}, clear=True):
            with contextlib.redirect_stdout(io.StringIO()):
                prepare_release.main()

    def verify(self, cf=True):
        args = [
            "verify", "--mrpack", str(self.mrpack), "--version", "3.0.0-beta",
            "--minecraft-version", "26.3", "--fabric-loader", "0.19.5",
        ]
        if cf:
            args += ["--curseforge-zip", str(self.cf_zip), "--cf-metadata-dir", str(self.cf)]
        with patch("sys.argv", args), patch.dict("os.environ", {}, clear=True):
            verify_release.main()

    def test_changelog_stops_at_branch_boundary(self):
        self.assertEqual(
            prepare_release.extract_changelog(self.changelog, "3.0.0-beta"),
            "- Minecraft has been updated to 26.3.\n",
        )

    def test_prepare_without_curseforge(self):
        self.prepare("--skip-curseforge")
        self.assertEqual(self.notes.read_text(), "- Minecraft has been updated to 26.3.\n")

    def test_prepare_requires_curseforge_by_default(self):
        with self.assertRaisesRegex(SystemExit, "metadata directory"):
            self.prepare()

    def test_prepare_curseforge(self):
        self.prepare("--cf-metadata-dir", str(self.cf))

    def test_prepare_rejects_incomplete_curseforge(self):
        (self.cf / "extra.pw.toml").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "counts differ"):
            self.prepare("--cf-metadata-dir", str(self.cf))

    def test_verify_modrinth_only(self):
        self.verify(cf=False)

    def test_verify_both_editions(self):
        self.verify()

    def test_verify_rejects_jar_overrides_without_curseforge(self):
        self.archives(mr_extra={"overrides/mods/extra.jar": "jar"})
        with self.assertRaisesRegex(SystemExit, "JAR overrides"):
            self.verify(cf=False)

    def test_verify_rejects_different_overrides(self):
        self.archives(cf_extra={"overrides/config/extra.json": "{}"})
        with self.assertRaisesRegex(SystemExit, "overrides differ"):
            self.verify()

    def test_verify_rejects_wrong_curseforge_file(self):
        self.manifest["files"][0]["fileID"] = 3
        self.archives()
        with self.assertRaisesRegex(SystemExit, "metadata files"):
            self.verify()

    def test_verify_rejects_different_mod_lists(self):
        self.index["files"][0]["path"] = "mods/other.jar"
        self.archives()
        with self.assertRaisesRegex(SystemExit, "mod lists differ"):
            self.verify()

    def test_verify_rejects_wrong_loader(self):
        self.index["dependencies"]["fabric-loader"] = "0.19.4"
        self.archives()
        with self.assertRaisesRegex(SystemExit, "Loader version"):
            self.verify(cf=False)


if __name__ == "__main__":
    unittest.main()
