#!/usr/bin/env python3
"""Large-file guard -- keeps oversized files out of commits.

.gitignore only excludes known *categories* of large files (node_modules,
build artifacts, etc.) -- it can't catch a one-off large file by size alone
(a dropped video, a PDF export, an accidentally-committed local session
transcript). GitHub hard-rejects any push containing a file over 100MB and
warns at 50MB (recommending Git LFS); this script enforces both limits
locally, before a push ever has the chance to fail.

Two modes:
  --staged   check exactly what `git commit` is about to commit (this is
             what tools/hooks/pre-commit calls -- see that file).
  --scan     check every tracked file in the working tree (periodic audit,
             or a first check when rolling this out to a repo that might
             already be carrying something oversized).

Stdlib only. See 16_OPERA_FRAMEWORK.md R-M6 -- this is a multi-repo policy,
rolled out the same way OPERA.md is (tools/opera_trace_sync.py
--check-hygiene / --push-hygiene).

Usage:
    python tools/large_file_check.py --staged
    python tools/large_file_check.py --scan
    python tools/large_file_check.py --scan --warn-mb 30 --hard-mb 80
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WARN_MB = 50
DEFAULT_HARD_MB = 100


def run(*args):
    return subprocess.run(list(args), capture_output=True, text=True, cwd=REPO_ROOT)


def staged_paths():
    r = run("git", "diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [p for p in r.stdout.splitlines() if p]


def tracked_paths():
    r = run("git", "ls-files")
    return [p for p in r.stdout.splitlines() if p]


def check(paths, warn_mb, hard_mb):
    """Return (blocked, warned) -- lists of (path, size_mb)."""
    blocked, warned = [], []
    for p in paths:
        full = REPO_ROOT / p
        if not full.is_file():
            continue  # deleted/renamed-away paths still appear in some git listings
        size_mb = full.stat().st_size / (1024 * 1024)
        if size_mb >= hard_mb:
            blocked.append((p, size_mb))
        elif size_mb >= warn_mb:
            warned.append((p, size_mb))
    return blocked, warned


def main():
    ap = argparse.ArgumentParser(description="Large-file guard")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="check files staged for commit")
    mode.add_argument("--scan", action="store_true", help="check every tracked file")
    ap.add_argument("--warn-mb", type=float, default=DEFAULT_WARN_MB)
    ap.add_argument("--hard-mb", type=float, default=DEFAULT_HARD_MB)
    args = ap.parse_args()

    paths = staged_paths() if args.staged else tracked_paths()
    blocked, warned = check(paths, args.warn_mb, args.hard_mb)

    if not blocked and not warned:
        if args.staged:
            print(f"large-file check: {len(paths)} staged file(s), all under {args.warn_mb:.0f}MB. OK.")
        else:
            print(f"large-file check: {len(paths)} tracked file(s), all under {args.warn_mb:.0f}MB. OK.")
        return 0

    for p, mb in warned:
        print(f"WARNING: {p} is {mb:.1f}MB (>= {args.warn_mb:.0f}MB) -- under GitHub's hard limit but worth a second look (Git LFS candidate?)")
    for p, mb in blocked:
        print(f"BLOCKED: {p} is {mb:.1f}MB (>= {args.hard_mb:.0f}MB) -- GitHub will reject this on push")

    if blocked:
        print(f"\n{len(blocked)} file(s) over the hard limit.", file=sys.stderr)
        if args.staged:
            print("Commit refused. Unstage the file(s) above (git restore --staged <path>) or add them to .gitignore.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
