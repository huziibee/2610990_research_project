# Gemini prompt helper

This small command-line helper sends a prompt to Google's `gemma-4-26b-a4b-it` model and prints a brief rationale summary followed by the answer. The model's private chain-of-thought is not exposed.

## Setup

No third-party packages are required. Use the Python launcher available on Windows:

```powershell
py --version
```

Copy `.env.example` to `.env` and put the API key after `GEMINI_API_KEY=`. The `.env` file is ignored by Git.

## Ask a prompt

```powershell
py .\gemini_prompt.py "Explain the difference between precision and recall."
```

Or run it without an argument to enter a prompt interactively:

```powershell
py .\gemini_prompt.py
```

You can also pipe prompt text to the script. Requests disable Gemma thinking with `thinkingLevel: minimal` and `includeThoughts: false`.
