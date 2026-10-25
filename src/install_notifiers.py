#!/usr/bin/env python3
"""
Installs (or removes) the notifier workflow in all your repositories.

On every push the notifier tells the gitlog.svg repository to refresh the card.

Requirements:
  - GitHub CLI (`gh`), logged in: gh auth login
  - GITLOG_TOKEN environment variable: fine-grained token scoped to the
    gitlog.svg repository only (see README)

Examples:
  python src/install_notifiers.py --dry-run
  python src/install_notifiers.py --repos a,b --dry-run
  python src/install_notifiers.py
  python src/install_notifiers.py --remove
"""

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

HUB_REPO = "gitlog.svg"
WORKFLOW_PATH = ".github/workflows/gitlog-notify.yml"
SECRET_NAME = "GITLOG_TOKEN"
TEMPLATE = Path(__file__).resolve().parent / "notify.yml"


def gh(*args, input_text=None):
    return subprocess.run(
        ["gh", *args], input=input_text, capture_output=True, text=True
    )


def list_repos(owner):
    """Non-fork, non-archived repos owned by `owner`, as [(full_name, default_branch)]."""
    result = gh(
        "api", "--paginate", "user/repos?per_page=100&affiliation=owner",
        "--jq",
        '.[] | select(.fork==false and .archived==false and .owner.login=="%s")'
        ' | "\\(.full_name)\\t\\(.default_branch)"' % owner,
    )
    if result.returncode != 0:
        sys.exit(f"Could not list your repositories:\n{result.stderr}")
    repos = []
    for line in result.stdout.splitlines():
        name, branch = line.split("\t")
        repos.append((name, branch))
    return repos


def existing_sha(full_name, branch):
    """SHA of the workflow file if it exists (needed to update or delete it)."""
    result = gh(
        "api", f"repos/{full_name}/contents/{WORKFLOW_PATH}?ref={branch}", "--jq", ".sha"
    )
    return result.stdout.strip() if result.returncode == 0 else None


def install(full_name, branch, owner, token, dry_run):
    content = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__BRANCH__", branch)
        .replace("__OWNER__", owner)
    )
    if dry_run:
        print(f"[dry-run] {full_name}: would create {WORKFLOW_PATH} (branch {branch}) and secret {SECRET_NAME}")
        return True

    sha = existing_sha(full_name, branch)
    args = [
        "api", "-X", "PUT", f"repos/{full_name}/contents/{WORKFLOW_PATH}",
        "-f", "message=chore: add gitlog notifier",
        "-f", f"content={base64.b64encode(content.encode()).decode()}",
        "-f", f"branch={branch}",
    ]
    if sha:
        args += ["-f", f"sha={sha}"]
    put = gh(*args)
    if put.returncode != 0:
        print(f"FAILED  {full_name}: could not create workflow ({put.stderr.strip()[:120]})")
        return False

    secret = gh("secret", "set", SECRET_NAME, "--repo", full_name, input_text=token)
    if secret.returncode != 0:
        print(f"FAILED  {full_name}: workflow created, but not the secret ({secret.stderr.strip()[:120]})")
        return False

    print(f"ok      {full_name}")
    return True


def remove(full_name, branch, dry_run):
    if dry_run:
        print(f"[dry-run] {full_name}: would delete {WORKFLOW_PATH} and secret {SECRET_NAME}")
        return True

    sha = existing_sha(full_name, branch)
    if sha:
        gh(
            "api", "-X", "DELETE", f"repos/{full_name}/contents/{WORKFLOW_PATH}",
            "-f", "message=chore: remove gitlog notifier",
            "-f", f"sha={sha}", "-f", f"branch={branch}",
        )
    gh("secret", "delete", SECRET_NAME, "--repo", full_name)
    print(f"removed {full_name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Install the gitlog notifier in your repositories.")
    parser.add_argument("--owner", default="joaopssx", help="your GitHub username")
    parser.add_argument("--repos", help="comma-separated list (e.g. a,b). Default: all")
    parser.add_argument("--dry-run", action="store_true", help="only show what would be done")
    parser.add_argument("--remove", action="store_true", help="uninstall instead of install")
    args = parser.parse_args()

    token = os.environ.get("GITLOG_TOKEN", "")
    if not args.dry_run and not args.remove and not token:
        sys.exit("Set the GITLOG_TOKEN environment variable first (see README).")

    if args.repos:
        # Branch is unknown for hand-picked repos, so assume "main".
        repos = [(f"{args.owner}/{r.strip()}", "main") for r in args.repos.split(",") if r.strip()]
    else:
        repos = list_repos(args.owner)

    repos = [(n, b) for n, b in repos if n.split("/")[1] != HUB_REPO]
    print(f"{len(repos)} repositories to process.\n")

    results = []
    for name, branch in repos:
        if args.remove:
            results.append(remove(name, branch, args.dry_run))
        else:
            results.append(install(name, branch, args.owner, token, args.dry_run))

    ok = sum(results)
    print(f"\nDone: {ok} ok, {len(results) - ok} failed.")


if __name__ == "__main__":
    main()
