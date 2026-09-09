#!/usr/bin/env python3

import argparse
import json
import os
import zipfile
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(message)


def jar_overrides(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if name.lower().endswith(".jar")
        and (name.startswith("overrides/") or name.startswith("client-overrides/"))
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mrpack", type=Path, required=True)
    parser.add_argument("--curseforge-zip", type=Path, required=True)
    parser.add_argument("--cf-metadata-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--minecraft-version", required=True)
    parser.add_argument("--fabric-loader", required=True)
    args = parser.parse_args()

    with zipfile.ZipFile(args.mrpack) as archive:
        names = archive.namelist()
        if "modrinth.index.json" not in names:
            fail("mrpack has no modrinth.index.json")
        index = json.loads(archive.read("modrinth.index.json"))
        unexpected = jar_overrides(names)
        if unexpected:
            fail(f"mrpack contains JAR overrides: {unexpected}")

    if index.get("versionId") != args.version:
        fail("mrpack version does not match the requested version")
    dependencies = index.get("dependencies", {})
    if dependencies.get("minecraft") != args.minecraft_version:
        fail("mrpack Minecraft version does not match")
    if dependencies.get("fabric-loader") != args.fabric_loader:
        fail("mrpack Fabric Loader version does not match")

    with zipfile.ZipFile(args.curseforge_zip) as archive:
        names = archive.namelist()
        if "manifest.json" not in names:
            fail("CurseForge archive has no manifest.json")
        manifest = json.loads(archive.read("manifest.json"))
        unexpected = jar_overrides(names)
        if unexpected:
            fail(f"CurseForge overrides contain JAR files: {unexpected}")

    if manifest.get("version") != args.version:
        fail("CurseForge manifest version does not match the requested version")
    minecraft = manifest.get("minecraft", {})
    if minecraft.get("version") != args.minecraft_version:
        fail("CurseForge Minecraft version does not match")
    expected_loader = f"fabric-{args.fabric_loader}"
    loaders = [item.get("id") for item in minecraft.get("modLoaders", [])]
    if expected_loader not in loaders:
        fail("CurseForge Fabric Loader version does not match")

    expected_files = len(list(args.cf_metadata_dir.glob("*.pw.toml")))
    actual_files = len(manifest.get("files", []))
    if actual_files != expected_files:
        fail(f"CurseForge manifest contains {actual_files} mods, expected {expected_files}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## Release artifacts\n\n")
            summary.write(f"- Modrinth metadata entries: {len(index.get('files', []))}\n")
            summary.write(f"- CurseForge metadata entries: {actual_files}\n")
            summary.write("- JAR files in overrides: 0\n")


if __name__ == "__main__":
    main()
