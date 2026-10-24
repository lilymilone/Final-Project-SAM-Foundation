"""Start SAM SPACE with one command:  python run.py

Then open http://127.0.0.1:8000 and use the demo sign-in shown on the page.

Options:
  --port 8000      choose a port (or set PORT)
  --reset-db       delete the local database and re-create the demo workspace
  --open           open the app in your browser after it starts
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

if sys.version_info < (3, 11):
    sys.exit(f"SAM SPACE needs Python 3.11 or newer (found {sys.version.split()[0]}).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SAM SPACE")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reset-db", action="store_true", help="delete and re-seed the local database")
    parser.add_argument("--open", action="store_true", help="open the browser after starting")
    args = parser.parse_args()

    try:
        import uvicorn

        from backend.app.core.config import get_settings
        from backend.app.main import FRONTEND_DIST
    except ImportError as exc:
        sys.exit(f"Missing package ({exc.name}). Run:  pip install -r requirements.txt")

    settings = get_settings()
    if args.reset_db and settings.database_path.exists():
        settings.database_path.unlink()
        print("Deleted the local database. A fresh demo workspace will be created.")

    url = f"http://{args.host}:{args.port}"
    print("\n  SAM SPACE")
    print(f"  Open {url}")
    print(f"  .env files loaded: {', '.join(settings.env_files_loaded) or 'none'}")
    print(f"  AI provider: {settings.provider or 'none (add OPENAI_API_KEY or PORTKEY_API_KEY to .env)'}")
    if not (FRONTEND_DIST / "index.html").is_file():
        print("  Warning: frontend/dist is missing. Run: cd frontend && npm install && npm run build")
    print("  Press Ctrl+C to stop.\n")

    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.app.main:create_app", factory=True, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
