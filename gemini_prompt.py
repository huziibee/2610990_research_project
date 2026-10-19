"""Send one prompt to Gemini 2.5 Flash-Lite and print a rationale summary and answer."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "gemini-2.5-flash-lite"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def load_local_env() -> None:
    """Load simple KEY=VALUE entries from .env without overriding process values."""
    env_file = Path(__file__).with_name(".env")
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def get_prompt(argument: str | None) -> str:
    if argument:
        return argument
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        if prompt:
            return prompt
    return input("Prompt: ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask Gemini 2.5 Flash-Lite a prompt.")
    parser.add_argument("prompt", nargs="?", help="Prompt text; omit to enter it interactively or pipe it in")
    args = parser.parse_args()

    load_local_env()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is missing. Add it to the .env file; see .env.example.", file=sys.stderr)
        return 2

    prompt = get_prompt(args.prompt)
    if not prompt:
        print("Prompt cannot be empty.", file=sys.stderr)
        return 2

    payload = {
        "systemInstruction": {
            "parts": [{
                "text": (
                    "Answer the user's prompt. Return two clearly labeled sections: "
                    "Rationale summary, giving a brief explanation of the main considerations "
                    "without revealing private chain-of-thought; and Response, giving the direct answer."
                )
            }]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingBudget": -1}},
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as result:
            data = json.loads(result.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"Gemini API returned HTTP {exc.code}: {details}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError) as exc:
        print(f"Could not reach Gemini API: {exc}", file=sys.stderr)
        return 1

    text = "\n".join(
        part.get("text", "")
        for candidate in data.get("candidates", [])
        for part in candidate.get("content", {}).get("parts", [])
        if part.get("text")
    )
    print(text or "Gemini returned no text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
