#!/usr/bin/env python3

import argparse
import os
import re
import sys
import tomllib
from pathlib import Path


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
MINECRAFT_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]*$")
RELEASE_HEADING_RE = re.compile(
    r"^###\s+\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\s*$", re.MULTILINE
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(message: str) -> None:
    raise SystemExit(message)


def extract_changelog(path: Path, version_id: str) -> str:
    text = path.read_text(encoding="utf-8")
    heading = re.compile(rf"^###\s+{re.escape(version_id)}\s*$", re.MULTILINE)
    match = heading.search(text)
    if match is None:
        fail(f"{version_id} is missing from {path}")

    next_heading = RELEASE_HEADING_RE.search(text, match.end())
    section = text[match.end() : next_heading.start() if next_heading else len(text)]
    lines = section.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and DATE_RE.fullmatch(lines[0].strip()):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    body = "\n".join(lines)
    body = re.sub(r"(?m)^\*\s+", "- ", body).strip()
    if not body:
        fail(f"{version_id} has an empty changelog section")
    return body + "\n"


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--cf-metadata-dir", type=Path, required=True)
    parser.add_argument("--changelog-file", type=Path, required=True)
    parser.add_argument("--release-notes", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--stage", choices=("alpha", "beta", "release"), required=True)
    parser.add_argument("--minecraft-version", required=True)
    parser.add_argument("--pack-name", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--artifact-prefix", required=True)
    args = parser.parse_args()

    if not VERSION_RE.fullmatch(args.version):
        fail("version must use the x.y.z format without a stage suffix")
    if not MINECRAFT_RE.fullmatch(args.minecraft_version):
        fail("minecraft_version contains unsupported characters")

    version_id = args.version if args.stage == "release" else f"{args.version}-{args.stage}"
    pack_toml = args.pack_dir / "pack.toml"
    if not pack_toml.is_file():
        fail(f"missing {pack_toml}")
    if not args.cf_metadata_dir.is_dir():
        fail(f"missing {args.cf_metadata_dir}")

    with pack_toml.open("rb") as source:
        pack = tomllib.load(source)
    if pack.get("name") != args.pack_name:
        fail(f"pack.toml name is {pack.get('name')!r}, expected {args.pack_name!r}")
    if pack.get("version") != version_id:
        fail(f"pack.toml version is {pack.get('version')!r}, expected {version_id!r}")
    minecraft = pack.get("versions", {}).get("minecraft")
    if minecraft != args.minecraft_version:
        fail(
            f"pack.toml Minecraft version is {minecraft!r}, "
            f"expected {args.minecraft_version!r}"
        )

    source_mods = sorted((args.pack_dir / "mods").glob("*.pw.toml"))
    cf_mods = sorted(args.cf_metadata_dir.glob("*.pw.toml"))
    if not source_mods or len(source_mods) != len(cf_mods):
        fail(
            "Modrinth and CurseForge metadata counts differ: "
            f"{len(source_mods)} != {len(cf_mods)}"
        )

    for metadata_path in cf_mods:
        with metadata_path.open("rb") as source:
            metadata = tomllib.load(source)
        if "curseforge" not in metadata.get("update", {}):
            fail(f"missing CurseForge update metadata in {metadata_path}")
        if metadata.get("download", {}).get("mode") != "metadata:curseforge":
            fail(f"unexpected download mode in {metadata_path}")

    custom_changelog = os.environ.get("CUSTOM_CHANGELOG", "").strip()
    if custom_changelog:
        release_notes = custom_changelog + "\n"
    else:
        release_notes = extract_changelog(args.changelog_file, version_id)
    args.release_notes.write_text(release_notes, encoding="utf-8", newline="\n")

    stage_name = "" if args.stage == "release" else f" {args.stage.title()}"
    write_output("version_id", version_id)
    write_output("display_name", f"{args.display_name} {args.version}{stage_name}")
    write_output("github_name", f"{args.version}{stage_name}")
    write_output("artifact_name", f"{args.artifact_prefix}-{version_id}")


if __name__ == "__main__":
    main()
