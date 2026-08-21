"""Interactive Gmail OAuth bootstrap for the worker container."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from worker.gmail_client import run_oauth_flow


def main() -> int:
    credentials_path = Path(
        os.environ.get("GMAIL_CREDENTIALS_PATH", "/secrets/credentials.json")
    )
    token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", "/secrets/token.json"))
    if not credentials_path.exists():
        print(f"Missing credentials file: {credentials_path}", file=sys.stderr)
        return 1
    run_oauth_flow(credentials_path, token_path)
    print(f"Wrote Gmail token to {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
