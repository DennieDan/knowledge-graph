"""Run the assistant connector over stdio, for Claude Desktop or Claude Code on this machine.

Run from apps/api with the virtual environment active:

    CONNECTOR_KEY=ck_... python -m scripts.connector_stdio

It reads the database in apps/api/.env. The key decides the company, the person
and the role, exactly as it does over HTTP (app/connector.py). Create one in
settings or with `python -m scripts.connector_key create`.
"""
import os
import sys

from app.connector import server, use_key


def main() -> None:
    if use_key(os.environ.get("CONNECTOR_KEY")) is None:
        print("CONNECTOR_KEY is missing, unknown, switched off, or its holder's role cannot connect.", file=sys.stderr)
        sys.exit(1)
    server.run("stdio")


if __name__ == "__main__":
    main()
