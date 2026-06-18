"""`minder swarm` CLI — observe and control swarms from the terminal (CLI/OBS).

Talks to the Minder server's swarm HTTP routes, so a human can replace the
orchestrator: list swarms, inspect who-is-doing-what, and approve manifests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from ..utils.common import base_http_url
from ..utils.config import require_client_settings


def _settings(args: argparse.Namespace) -> tuple[str, str]:
    payload = require_client_settings(Path(args.config_path))
    base = base_http_url(str(payload.get("server_url", "")).strip())
    client_key = str(payload.get("client_api_key", "")).strip()
    return base, client_key


def _headers(client_key: str) -> dict[str, str]:
    return {"X-Minder-Client-Key": client_key}


def swarm_list_command(args: argparse.Namespace) -> int:
    base, key = _settings(args)
    resp = httpx.get(f"{base}/api/v1/swarms", headers=_headers(key), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    swarms = data.get("swarms", [])
    if not swarms:
        print("No swarms.")
        return 0
    for s in swarms:
        print(f"{s['swarm_id']}  [{s['status']:<14}]  {s['goal']}")
    return 0


def swarm_who_command(args: argparse.Namespace) -> int:
    base, key = _settings(args)
    resp = httpx.get(f"{base}/api/v1/swarms/{args.swarm_id}", headers=_headers(key), timeout=15)
    if resp.status_code == 404:
        print("Swarm not found.", file=sys.stderr)
        return 1
    resp.raise_for_status()
    d = resp.json()
    print(f"Swarm {d['swarm_id']} [{d['status']}] — {d['goal']}\n")
    print("NODES (who/where):")
    for n in d.get("nodes", []):
        task = n.get("current_task_id") or "-"
        print(f"  {n['runtime']:<10} {n['status']:<8} ws={n['workspace'] or '-':<20} task={task}")
    print("\nTASKS (board):")
    for t in d.get("tasks", []):
        dep = ",".join(t.get("depends_on") or []) or "-"
        print(f"  [{t['status']:<11}] {t['title']:<30} hint={t.get('runtime_hint') or '-':<10} deps={dep}")
    m = d.get("manifest")
    if m:
        print(f"\nMANIFEST: status={m['status']}  ({m.get('estimated_cost_note', '')})")
    return 0


def swarm_board_command(args: argparse.Namespace) -> int:
    # Alias of who, but emits raw JSON for scripting.
    base, key = _settings(args)
    resp = httpx.get(f"{base}/api/v1/swarms/{args.swarm_id}", headers=_headers(key), timeout=15)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))
    return 0


def swarm_approve_command(args: argparse.Namespace) -> int:
    base, key = _settings(args)
    body: dict = {"action": args.action, "approved_by": "cli"}
    if args.workers_file:
        body["workers"] = json.loads(Path(args.workers_file).read_text())
    resp = httpx.post(
        f"{base}/api/v1/swarms/{args.swarm_id}/approve",
        headers=_headers(key),
        json=body,
        timeout=15,
    )
    if resp.status_code >= 400:
        print(f"Error: {resp.text}", file=sys.stderr)
        return 1
    print(json.dumps(resp.json(), indent=2))
    return 0


def register_swarm_parser(subparsers: argparse._SubParsersAction, client_config_path) -> None:
    swarm = subparsers.add_parser("swarm", help="Observe and control agent swarms.")
    sub = swarm.add_subparsers(dest="swarm_command", metavar="<subcommand>")

    def _add_config(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config-path", default=str(client_config_path()), help="Path to client config.")

    p_list = sub.add_parser("list", help="List swarms.")
    _add_config(p_list)
    p_list.set_defaults(func=swarm_list_command)

    p_who = sub.add_parser("who", help="Show who is doing what, where (presence + board).")
    p_who.add_argument("swarm_id")
    _add_config(p_who)
    p_who.set_defaults(func=swarm_who_command)

    p_board = sub.add_parser("board", help="Dump full swarm state as JSON.")
    p_board.add_argument("swarm_id")
    _add_config(p_board)
    p_board.set_defaults(func=swarm_board_command)

    p_appr = sub.add_parser("approve", help="Approve/edit/reject a swarm manifest (human gate).")
    p_appr.add_argument("swarm_id")
    p_appr.add_argument("--action", choices=("approve", "edit", "reject"), default="approve")
    p_appr.add_argument("--workers-file", help="JSON file of edited worker specs (with --action edit).")
    _add_config(p_appr)
    p_appr.set_defaults(func=swarm_approve_command)
