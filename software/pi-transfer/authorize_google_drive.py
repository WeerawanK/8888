"""Create a fresh Google Drive OAuth token on a computer with a browser."""

from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("client_file", type=Path)
    parser.add_argument("token_file", type=Path)
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_file),
        SCOPES,
    )
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )
    args.token_file.parent.mkdir(parents=True, exist_ok=True)
    args.token_file.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Fresh Google token saved to: {args.token_file}")


if __name__ == "__main__":
    main()
