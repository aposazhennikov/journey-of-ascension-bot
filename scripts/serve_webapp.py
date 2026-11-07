"""Serve the 3D meridian map locally without starting the Telegram bot.

Usage:
    python3 scripts/serve_webapp.py [--port 8767]
Then open http://127.0.0.1:8767/webapp/?lang=ru
"""

import argparse
import json
import sys
import types
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# bot.utils imports aiofiles only for async loading, which this preview does not use.
sys.modules.setdefault("aiofiles", types.ModuleType("aiofiles"))

from bot.utils import MeridiansManager  # noqa: E402
from bot.webapp import setup_webapp_routes  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()

    manager = MeridiansManager(str(ROOT / "bot" / "meridians.json"))
    manager._meridians = json.loads((ROOT / "bot" / "meridians.json").read_text(encoding="utf-8"))

    app = web.Application()
    setup_webapp_routes(app, manager)
    print(f"3D meridian map: http://{args.host}:{args.port}/webapp/?lang=ru")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
