"""Check recorded freeze manifests against the Git commits that created them.

Needs a Git clone (not a source export). Read-only. Exit 0 only if:
- every results/phase2_freeze.json hash equals the blob at the Phase 2 commit;
- every results/phase3_validation_manifest.json hash equals the blob at the Phase 3 commit;
- immutable evidence (data/ and results/) is unchanged at HEAD;
- engineering logs changed since then only by appending.
Other source/doc changes at HEAD are listed, not treated as corruption.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PHASE2_COMMIT = "cf4e41c"
PHASE3_COMMIT = "18d11d6"
APPEND_ONLY = ("docs/ai_log.md", "docs/effort.md")


def blob(commit, path):
    result = subprocess.run(["git", "show", f"{commit}:{path}"], capture_output=True, check=True)
    return result.stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    problems, evolved = [], set()
    phase2 = json.loads(Path("results/phase2_freeze.json").read_text())["files"]
    phase3 = json.loads(Path("results/phase3_validation_manifest.json").read_text())
    phase3 = {**phase3["files"], **phase3["unchanged_numeric_evidence"]}
    for commit, manifest in ((PHASE2_COMMIT, phase2), (PHASE3_COMMIT, phase3)):
        for path, recorded in sorted(manifest.items()):
            if digest(blob(commit, path)) != recorded:
                problems.append(f"{path}: manifest does not match {commit}")
            current = Path(path).read_bytes()
            if digest(current) != recorded:
                if path.startswith(("data/", "results/")):
                    problems.append(f"{path}: immutable evidence changed at HEAD")
                elif path in APPEND_ONLY and not current.startswith(blob(commit, path)):
                    problems.append(f"{path}: log was rewritten, not appended")
                else:
                    evolved.add(path)
    for path in sorted(evolved):
        print(f"evolved since freeze (expected): {path}")
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if problems:
        return 1
    print(
        f"PASS: {len(phase2)} Phase 2 and {len(phase3)} Phase 3 hashes match their commits; "
        "immutable evidence unchanged; logs append-only"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
