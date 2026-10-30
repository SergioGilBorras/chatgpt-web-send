"""Command-line interface for chatgpt-web-send."""

from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from .client import BASE_URL, ChatGPTWeb, ChatGPTWebError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt-web-send", description="Send prompts through an authenticated ChatGPT browser tab."
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.2")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile-dir", type=Path, help="Persistent browser profile directory")
    common.add_argument(
        "--downloads-dir", type=Path,
        help="Folder for permanent browser downloads (default: ~/Downloads)",
    )
    common.add_argument(
        "--browser-channel", choices=("chrome", "msedge"),
        help="Use installed Chrome or Edge; default is Playwright Chromium",
    )
    common.add_argument("--timeout", type=float, default=60.0, help="UI timeout in seconds (default: 60)")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("login", parents=[common], help="Sign in interactively (once)")
    doctor = subcommands.add_parser(
        "doctor", parents=[common], help="Show the actual browser, profile and download settings"
    )
    doctor.add_argument("--keep-open", action="store_true",
                        help="Inspect the browser visually until Enter is pressed")
    doctor.add_argument("--headless", action="store_true",
                        help="Run browser startup diagnostics without a visible window")
    normal = subcommands.add_parser(
        "open", help="Open ChatGPT in your regular system browser (manual mode)"
    )
    normal.add_argument("--conversation-id", help="Existing conversation ID (optional)")
    send = subcommands.add_parser("send", parents=[common], help="Send to an existing conversation")
    send.add_argument("--conversation-id", required=True, help="ID from chatgpt.com/c/<id>")
    prompt_source = send.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt", help="Prompt as a command-line string")
    prompt_source.add_argument("--prompt-file", type=Path, help="UTF-8 file containing the prompt")
    prompt_source.add_argument("--stdin", action="store_true", help="Read prompt from standard input")
    send.add_argument("--headless", action="store_true", help="Use a hidden browser (requires prior login)")
    send.add_argument("--no-wait", action="store_true", help="Do not watch generation controls")
    send.add_argument("--completion-timeout", type=float, default=300.0, help="Max seconds to watch generation")
    send.add_argument("--keep-open", action="store_true", help="Keep the browser open until Enter is pressed")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "open":
        identifier = args.conversation_id
        if identifier is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", identifier):
            print("Error: invalid conversation ID", file=sys.stderr)
            return 2
        url = f"{BASE_URL}/c/{identifier}" if identifier else BASE_URL
        # Open the user's genuine daily browser/profile, without attaching
        # Playwright or accessing cookies, history or existing tabs.
        if not webbrowser.open_new_tab(url):
            print("Could not open the system browser", file=sys.stderr)
            return 1
        print("Opened in your regular browser. Write and send the message manually.")
        return 0
    if args.command == "send" and args.headless and args.keep_open:
        print("Error: --keep-open requires a visible browser", file=sys.stderr)
        return 2
    try:
        with ChatGPTWeb(profile_dir=args.profile_dir, timeout=args.timeout,
                        headless=getattr(args, "headless", False),
                        browser_channel=args.browser_channel,
                        downloads_dir=args.downloads_dir) as client:
            if args.command == "doctor":
                info = client.browser_info()
                print(f"Actual browser channel: {info['channel']}")
                print(f"Browser User-Agent: {info['user_agent']}")
                print(f"Persistent profile: {info['profile_dir']}")
                print(f"Saved downloads: {info['downloads_dir']}")
                if args.keep_open:
                    print("Browser is open for inspection. Press Enter to close.")
                    input()
            elif args.command == "login":
                client.open_login()
                print("Sign in to ChatGPT in the browser. Before pressing Enter,")
                print("confirm the normal chat editor is visible, with no verification challenge.")
                print("If a CAPTCHA keeps returning, stop; this tool cannot bypass it.")
                input()
                print("Browser profile saved locally; do not commit it to Git.")
            else:
                if args.prompt is not None:
                    prompt = args.prompt
                elif args.prompt_file is not None:
                    prompt = args.prompt_file.read_text(encoding="utf-8")
                else:
                    prompt = sys.stdin.read()
                try:
                    result = client.send(
                        conversation_id=args.conversation_id,
                        prompt=prompt,
                        wait=not args.no_wait,
                        completion_timeout=args.completion_timeout,
                    )
                except (ChatGPTWebError, PlaywrightError, OSError, ValueError) as exc:
                    if args.keep_open:
                        print(f"Error: {exc}", file=sys.stderr)
                        print("Browser left open for inspection. Press Enter to close it.")
                        try:
                            input()
                        except EOFError:
                            pass
                        return 1
                    raise
                print(f"Prompt submitted to {result.url}")
                if result.completed is True:
                    print("Generation finished (based on UI controls; response not read).")
                elif not args.no_wait:
                    print("Could not verify generation completion from UI controls.")
                if args.keep_open:
                    print("Press Enter to close the browser.")
                    input()
        return 0
    except (ChatGPTWebError, PlaywrightError, OSError, ValueError, EOFError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
