"""Cold backup and restore for the single-host Compose deployment."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("database.dump", "documents.tar")


def compose(project, *args, **kwargs):
    return subprocess.run(["docker", "compose", "-p", project, *args], cwd=ROOT, check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup(project, folder):
    running = compose(
        project, "ps", "--services", "--status", "running", capture_output=True, text=True
    ).stdout.split()
    if not {"backend", "postgres", "worker"}.issubset(running):
        raise SystemExit("Start the source project before backup.")
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    try:
        compose(project, "stop", "backend", "worker")
        with (folder / FILES[0]).open("wb") as out:
            compose(
                project,
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "pilot",
                "-d",
                "claims",
                "-Fc",
                "--no-acl",
                "--no-owner",
                "--exclude-table-data=sessions",
                stdout=out,
            )
        with (folder / FILES[1]).open("wb") as out:
            compose(
                project,
                "run",
                "--rm",
                "-T",
                "--no-deps",
                "backend",
                "sh",
                "-ec",
                "cd /srv/state && find . -maxdepth 1 -type f -name '*.upload' -print0 | tar --null -T - -cf -",
                stdout=out,
            )
        (folder / "manifest.json").write_text(
            json.dumps({name: digest(folder / name) for name in FILES}, indent=2)
        )
    finally:
        compose(project, "start", "backend", "worker")


def restore(project, folder):
    expected = json.loads((folder / "manifest.json").read_text())
    if expected != {name: digest(folder / name) for name in FILES}:
        raise SystemExit("Backup checksum mismatch.")
    with tarfile.open(folder / FILES[1]) as archive:
        for member in archive:
            if not member.isfile() or not re.fullmatch(r"(?:\./)?[0-9a-f]{32}\.upload", member.name):
                raise SystemExit("Unexpected document archive member.")
    for resource in ("volume", "container", "network"):
        flags = ["-aq"] if resource == "container" else ["-q"]
        existing = subprocess.check_output(
            ["docker", resource, "ls", *flags, "--filter", "label=com.docker.compose.project=" + project]
        )
        if existing.strip():
            raise SystemExit("Choose a fresh Compose project name for recovery.")
    compose(project, "up", "-d", "--wait", "postgres")
    with (folder / FILES[0]).open("rb") as stream:
        compose(
            project,
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "pilot",
            "-d",
            "claims",
            "--single-transaction",
            "--no-acl",
            "--no-owner",
            stdin=stream,
        )
    compose(project, "build", "backend")
    with (folder / FILES[1]).open("rb") as stream:
        compose(
            project,
            "run",
            "--rm",
            "-T",
            "--no-deps",
            "backend",
            "tar",
            "--no-same-owner",
            "-xf",
            "-",
            "-C",
            "/srv/state",
            stdin=stream,
        )
    compose(project, "up", "-d", "--wait", "backend", "worker")
    # Check every database reference against the restored private files.
    verify = """from app.db import Document, Session
from app.documents import path_for
from hashlib import file_digest
with Session() as db:
    for doc in db.query(Document).yield_per(100):
        with path_for(doc).open('rb') as stream:
            if file_digest(stream,'sha256').hexdigest()!=doc.digest:
                raise ValueError('Document checksum mismatch: '+doc.id)
print('Restored document references verified.')
"""
    compose(project, "exec", "-T", "backend", "python", "-c", verify)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("project", type=str)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.project):
        parser.error("Use a Docker Compose project name.")
    if os.name != "nt":
        os.umask(0o077)
    (backup if args.action == "backup" else restore)(args.project, args.folder.resolve())
