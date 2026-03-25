"""
get_youtube_token.py
─────────────────────
ONE-TIME SCRIPT to generate a YouTube OAuth2 Refresh Token.

Run this locally (NOT in CI/CD) ONCE before deploying the agent:
  python get_youtube_token.py

Then copy the printed YOUTUBE_REFRESH_TOKEN into your .env file
and GitHub Actions secrets.

Requirements:
  pip install google-auth-oauthlib
"""

import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print("\n❌ ERROR: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env\n")
        return

    # Build client config dict (same format as client_secrets.json)
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("\n" + "=" * 60)
    print("YouTube OAuth2 Token Generator")
    print("=" * 60)
    print("\nThis will open a browser window for Google sign-in.")
    print("Sign in with the YouTube account you want to upload to.\n")

    creds = flow.run_local_server(
        port=3000,
        prompt="consent",
        access_type="offline",
        open_browser=False,
    )

    print("\n" + "=" * 60)
    print("✅ SUCCESS! Copy the values below into your .env file and GitHub Secrets:")
    print("=" * 60)
    print(f"\nYOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
    print("\n" + "=" * 60)

    # Optionally save to a local file for easy copy-paste
    token_data = {
        "YOUTUBE_CLIENT_ID": client_id,
        "YOUTUBE_CLIENT_SECRET": client_secret,
        "YOUTUBE_REFRESH_TOKEN": creds.refresh_token,
    }
    with open("youtube_token.json", "w") as f:
        json.dump(token_data, f, indent=2)
    print("\n📄 Also saved to: youtube_token.json (DO NOT commit this file!)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
