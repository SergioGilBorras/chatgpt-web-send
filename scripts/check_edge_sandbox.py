"""Windows Edge security smoke: inspect Playwright's actual launch command.

Uses Playwright DEBUG=pw:browser logs from an isolated subprocess rather than
enumerating potentially inaccessible Windows processes. It opens no websites,
uses no user session, and prints no personal paths or raw browser logs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        print("Windows Edge sandbox smoke test requires Windows", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="chatgpt-edge-sandbox-") as tmp:
        root = Path(tmp)
        env = dict(os.environ, DEBUG="pw:browser")
        result = subprocess.run(
            [
                sys.executable, "-m", "chatgpt_web_send", "doctor",
                "--browser-channel", "msedge", "--headless",
                "--profile-dir", str(root / "profile"),
                "--downloads-dir", str(root / "downloads"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
            timeout=90,
        )
        if result.returncode != 0:
            print("Sandboxed Edge could not start; check browser and Windows policies", file=sys.stderr)
            return 1
        launch_lines = [
            line for line in result.stderr.splitlines()
            if "<launching>" in line and "msedge.exe" in line.casefold()
        ]
        if not launch_lines:
            print("Playwright did not expose the Edge launch command in debug logs", file=sys.stderr)
            return 1
        if any("--no-sandbox" in line.casefold() for line in launch_lines):
            print("Security failure: Edge received --no-sandbox", file=sys.stderr)
            return 1
        if "Edg/" not in result.stdout:
            print("The expected Microsoft Edge User-Agent was not detected", file=sys.stderr)
            return 1
        print("Sandboxed Microsoft Edge launched: --no-sandbox absent, Edge UA verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
