"""Windows-only smoke test: Edge starts sandboxed without --no-sandbox.

This inspects only the command line of a temporary Edge process launched by
this test, never navigates to ChatGPT, and never reads cookies or messages.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from chatgpt_web_send import ChatGPTWeb


def main() -> int:
    if sys.platform != "win32":
        print("Windows Edge sandbox smoke test requires Windows", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="chatgpt-edge-sandbox-") as tmp:
        root = Path(tmp)
        # Dedicated temporary profile. Do not use or modify any personal profile.
        with ChatGPTWeb(
            profile_dir=root / "profile",
            downloads_dir=root / "downloads",
            browser_channel="msedge",
            headless=True,
        ) as client:
            client._page().goto("data:text/html,<title>Sandbox%20smoke</title>")
            process = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" "
                    "| ForEach-Object { $_.CommandLine }",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if process.returncode != 0:
                print("Unable to inspect Edge process command lines", file=sys.stderr)
                return 1
            needle = str(client.profile_dir.resolve()).casefold()
            commands = [
                line for line in process.stdout.splitlines()
                if "--user-data-dir=" in line.casefold() and
                needle in line.casefold().replace("/", "\\")
            ]
            if not commands:
                print("No Edge process matched the test's temporary profile", file=sys.stderr)
                return 1
            if any("--no-sandbox" in command.casefold() for command in commands):
                print("Edge was started with --no-sandbox: sandbox is not enabled", file=sys.stderr)
                return 1
            print("Edge launched with its sandbox enabled; no --no-sandbox found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
