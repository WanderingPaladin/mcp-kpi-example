"""Build the anonymous Greenhouse ZIP and run submission checks."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUB = Path(__file__).resolve().parent
ARTIFACTS = Path("/opt/cursor/artifacts")
ZIP_NAME = "kpi-assistant-take-home.zip"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "submission",
}
SKIP_FILE_NAMES = {".env", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".webp", ".mp4"}

FORBIDDEN = [
    re.compile(r"\bRiley\b", re.I),
    re.compile(r"WanderingPaladin", re.I),
    re.compile(r"cursoragent@", re.I),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIR_NAMES:
        return True
    if path.name in SKIP_FILE_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def iter_source_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if should_skip(rel):
            continue
        yield path, Path("source") / rel


def write_zip(dest: Path) -> list[str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    contents = (
        "Anonymous submission (no candidate name).\n"
        "\n"
        "DESIGN.pdf       Written review packet: architecture, tools, decisions, AI use.\n"
        "RUNBOOK.pdf      How to run on Windows and macOS/Linux.\n"
        "DATA-NOTES.pdf   Calculation/source-of-truth note (CSV, not Excel).\n"
        "source/          Application code, tests, sample CSV, .env.example.\n"
        "\n"
        "Excluded on purpose: .env, virtualenv, node_modules, .git, personal names.\n"
        "Upload this ZIP once through Greenhouse. Do not upload a RAR.\n"
    )
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("CONTENTS.txt", contents)
        names.append("CONTENTS.txt")
        for pdf in ("DESIGN.pdf", "RUNBOOK.pdf", "DATA-NOTES.pdf"):
            zf.write(SUB / pdf, pdf)
            names.append(pdf)
        for src, arc in iter_source_files():
            zf.write(src, arc.as_posix())
            names.append(arc.as_posix())
    return names


def scan_zip(dest: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(dest) as zf:
        namelist = zf.namelist()
        if any(n.endswith(".env") and not n.endswith(".env.example") for n in namelist):
            problems.append("ZIP contains a .env file")
        if any(".venv/" in n or n.endswith(".venv") for n in namelist):
            problems.append("ZIP contains a virtualenv")
        if any("node_modules/" in n for n in namelist):
            problems.append("ZIP contains node_modules")
        if any(n.startswith(".git/") or "/.git/" in n for n in namelist):
            problems.append("ZIP contains .git history (identity leak risk)")
        if any(n.lower().endswith(".rar") for n in namelist):
            problems.append("ZIP contains a RAR")
        for name in namelist:
            if name.endswith((".pdf", ".md", ".py", ".txt", ".example", ".yml", ".json", ".ts", ".tsx", ".css")):
                raw = zf.read(name)
                try:
                    text = raw.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                for pat in FORBIDDEN:
                    if pat.search(text):
                        problems.append(f"{name}: matched {pat.pattern}")
    return problems


def main() -> None:
    names = write_zip(SUB / ZIP_NAME)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    artifact = ARTIFACTS / ZIP_NAME
    artifact.write_bytes((SUB / ZIP_NAME).read_bytes())
    problems = scan_zip(SUB / ZIP_NAME)
    print(f"files={len(names)}")
    print(f"bytes={(SUB / ZIP_NAME).stat().st_size}")
    print(f"artifact={artifact}")
    if problems:
        print("PROBLEMS")
        for item in problems:
            print(" -", item)
        raise SystemExit(1)
    print("CHECKS_OK")
    for item in sorted(names)[:20]:
        print(" ", item)
    print(" ...")
    for required in ("DESIGN.pdf", "RUNBOOK.pdf", "DATA-NOTES.pdf", "source/README.md", "source/data/kpi_sample_2000.csv", "source/.env.example"):
        print("required", required, required in names)


if __name__ == "__main__":
    main()
