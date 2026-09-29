"""Manage the day13-chat prompt versions and the `production` label on Langfuse.

    python scripts/prompt_versions.py setup     # create v1 (baseline, production) and v2 (candidate)
    python scripts/prompt_versions.py show      # print every version with its labels
    python scripts/prompt_versions.py promote   # move production -> v2
    python scripts/prompt_versions.py rollback  # move production -> v1

Label moves only change which version the API fetches; restart the API afterwards so the
in-process prompt cache is dropped.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

V1_TEMPLATE = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2_TEMPLATE = "Answer in no more than three concise bullet points.\n" + V1_TEMPLATE
REQUIRED_VARIABLES = ("{{feature}}", "{{docs}}", "{{message}}")


def get_version(client, name: str, version: int):
    try:
        return client.get_prompt(name, version=version, type="text", cache_ttl_seconds=0, max_retries=0)
    except Exception:
        return None


def setup(client, name: str) -> None:
    for template in (V1_TEMPLATE, V2_TEMPLATE):
        assert all(v in template for v in REQUIRED_VARIABLES)

    if get_version(client, name, 1) is None:
        client.create_prompt(
            name=name, prompt=V1_TEMPLATE, labels=["baseline", "production"], type="text",
            commit_message="v1 baseline prompt",
        )
        print("Created v1 with labels baseline, production")
    else:
        print("v1 already exists; skipped")

    if get_version(client, name, 2) is None:
        client.create_prompt(
            name=name, prompt=V2_TEMPLATE, labels=["candidate"], type="text",
            commit_message="v2 candidate: concise bullet answers",
        )
        print("Created v2 with label candidate")
    else:
        print("v2 already exists; skipped")


def show(client, name: str) -> None:
    version = 1
    while (prompt := get_version(client, name, version)) is not None:
        first_line = prompt.prompt.splitlines()[0]
        print(f"{name} v{prompt.version}: labels={sorted(prompt.labels)} | first line: {first_line!r}")
        version += 1


def move_production(client, name: str, version: int) -> None:
    # Labels are unique per prompt, so assigning production here removes it from the other version.
    keep = {1: "baseline", 2: "candidate"}[version]
    client.update_prompt(name=name, version=version, new_labels=[keep, "production"])
    print(f"production -> v{version}")


def main() -> int:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["setup", "show", "promote", "rollback"])
    args = parser.parse_args()

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        print("LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set in .env")
        return 1

    from langfuse import get_client

    client = get_client()
    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    if args.action == "setup":
        setup(client, name)
    elif args.action == "promote":
        move_production(client, name, 2)
    elif args.action == "rollback":
        move_production(client, name, 1)
    show(client, name)
    client.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
