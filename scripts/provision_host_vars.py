#!/usr/bin/env python3
"""
provision_host_vars.py

Reads inventory/hosts.ini and creates a host_vars directory for any host
that does not already have one. The group a host belongs to drives which
skeleton files are copied:

  Group naming convention: <platform>_<stacking>

  Platform prefix → skeleton folder
    cx_   → inventory/skeleton/aoscx/
    eos_  → inventory/skeleton/eos/     (future)

  Stacking suffix → which stacking file is included
    _vsx  → vsx.yml copied,  vsf.yml skipped
    _vsf  → vsf.yml copied,  vsx.yml skipped
    none  → neither vsx.yml nor vsf.yml copied

Usage:
    # Provision all hosts in hosts.ini that don't yet have host_vars
    python scripts/provision_host_vars.py

    # Provision a specific host only
    python scripts/provision_host_vars.py --host cx-sw-03

    # Preview what would be created without writing any files
    python scripts/provision_host_vars.py --dry-run
"""

import argparse
import configparser
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR    = Path(__file__).parent
PROJECT_DIR   = SCRIPT_DIR.parent
HOSTS_FILE    = PROJECT_DIR / "inventory" / "hosts.ini"
SKELETON_DIR  = PROJECT_DIR / "inventory" / "skeleton"
HOST_VARS_DIR = PROJECT_DIR / "inventory" / "host_vars"

HOSTNAME_PLACEHOLDER = "__HOSTNAME__"

# ── Platform + stacking resolution ───────────────────────────────────────────

# Maps group name prefix → skeleton subdirectory name
PLATFORM_MAP = {
    "cx":   "aoscx",
    "exos": "extreme_exos",
    "voss": "extreme_voss",
}

# Stacking files — exactly one is included per device, or neither
STACKING_FILES = {
    "vsx": "vsx.yml",
    "vsf": "vsf.yml",
}


def resolve_group(group_name: str) -> tuple[str | None, str | None]:
    """
    Parse a group name into (platform_dir, stacking) from the convention
    <platform>_<stacking> or <platform>.

    Returns (platform_dir, stacking) where stacking may be None.
    Returns (None, None) if the group name is not recognised or is a
    meta-group (:children / :vars).
    """
    # Skip Ansible meta-sections
    if ":" in group_name:
        return None, None

    parts = group_name.split("_", 1)
    prefix = parts[0]
    suffix = parts[1] if len(parts) > 1 else None

    platform_dir = PLATFORM_MAP.get(prefix)
    if platform_dir is None:
        return None, None

    stacking = suffix if suffix in STACKING_FILES else None
    return platform_dir, stacking


# ── Inventory parsing ─────────────────────────────────────────────────────────

def parse_hosts(hosts_file: Path) -> dict[str, str]:
    """
    Return a flat {hostname: group_name} map, ignoring :children/:vars
    meta-sections and any groups not matching a known platform prefix.
    """
    parser = configparser.ConfigParser(allow_no_value=True)
    parser.read(hosts_file)

    result = {}
    for section in parser.sections():
        if ":" in section:
            continue
        platform_dir, _ = resolve_group(section)
        if platform_dir is None:
            continue
        for host in parser.options(section):
            if host and host not in result:
                result[host] = section

    return result


# ── Provisioning ──────────────────────────────────────────────────────────────

def provision_host(
    hostname: str,
    group: str,
    dry_run: bool = False,
) -> bool:
    """
    Create host_vars/<hostname>/ from the appropriate skeleton directory.
    Returns True if files were created, False if the directory already existed.
    """
    target_dir = HOST_VARS_DIR / hostname

    if target_dir.exists():
        print(f"  [skip]    {hostname}  —  host_vars already exists")
        return False

    platform_dir, stacking = resolve_group(group)
    skeleton_platform_dir = SKELETON_DIR / platform_dir

    if not skeleton_platform_dir.exists():
        print(
            f"  [error]   No skeleton directory found for platform "
            f"'{platform_dir}' at {skeleton_platform_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Determine which files to copy:
    # - Skip the stacking file that doesn't apply to this device
    # - Skip both if no stacking suffix on the group
    skip_files = set()
    for stack_key, stack_file in STACKING_FILES.items():
        if stacking != stack_key:
            skip_files.add(stack_file)

    skeleton_files = sorted(
        f for f in skeleton_platform_dir.glob("*.yml")
        if f.name not in skip_files
    )

    if not skeleton_files:
        print(f"  [error]   No skeleton files found in {skeleton_platform_dir}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        stacking_label = stacking or "none"
        print(
            f"  [dry-run] Would create: inventory/host_vars/{hostname}/  "
            f"(platform: {platform_dir}, stacking: {stacking_label})"
        )
        for f in skeleton_files:
            print(f"              {f.name}")
        return True

    target_dir.mkdir(parents=True)

    for skeleton_file in skeleton_files:
        content = skeleton_file.read_text()
        content = content.replace(HOSTNAME_PLACEHOLDER, hostname)
        (target_dir / skeleton_file.name).write_text(content)

    stacking_label = stacking or "none"
    print(
        f"  [created] inventory/host_vars/{hostname}/  "
        f"({len(skeleton_files)} files, platform: {platform_dir}, stacking: {stacking_label})"
    )
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Provision host_vars directories from skeleton files."
    )
    parser.add_argument(
        "--host",
        metavar="HOSTNAME",
        help="Provision a specific host only (must exist in hosts.ini)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing any files",
    )
    args = parser.parse_args()

    if not HOSTS_FILE.exists():
        print(f"Error: hosts file not found: {HOSTS_FILE}", file=sys.stderr)
        sys.exit(1)

    if not SKELETON_DIR.exists():
        print(f"Error: skeleton directory not found: {SKELETON_DIR}", file=sys.stderr)
        sys.exit(1)

    all_hosts = parse_hosts(HOSTS_FILE)

    if not all_hosts:
        print("No recognised hosts found in hosts.ini — nothing to do.")
        sys.exit(0)

    if args.host:
        if args.host not in all_hosts:
            print(
                f"Error: '{args.host}' not found in {HOSTS_FILE}\n"
                f"Known hosts: {', '.join(sorted(all_hosts))}",
                file=sys.stderr,
            )
            sys.exit(1)
        targets = {args.host: all_hosts[args.host]}
    else:
        targets = all_hosts

    if args.dry_run:
        print("Dry run — no files will be written.\n")

    # Group targets by their group for tidier output
    by_group: dict[str, list[str]] = {}
    for hostname, group in targets.items():
        by_group.setdefault(group, []).append(hostname)

    created = skipped = 0

    for group, hosts in sorted(by_group.items()):
        print(f"\n[{group}]")
        for hostname in sorted(hosts):
            result = provision_host(hostname, group, dry_run=args.dry_run)
            if result:
                created += 1
            else:
                skipped += 1

    print(f"\nDone.  Created: {created}  Skipped: {skipped}")


if __name__ == "__main__":
    main()
