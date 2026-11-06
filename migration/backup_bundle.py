#!/usr/bin/env python3
"""Verify and unpack an OFFLINE backup into a fresh rehearsal directory.

No network, SQL execution, Docker calls, deletion, or source modifications.
Archive links are intentionally rejected: resolve/review them in a backup copy,
never silently skip them. Run apply as root on a dedicated Linux test VM to
preserve numeric ownership. Verification also works on macOS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile

REQUIRED = {
    "database.sql": None,
    "community-data.tar.gz": "community-data",
    "mail-data.tar.gz": "mail-data",
    "configuration.tar.gz": "configuration",
}
BASELINE = {"communityserver": "12.8.0.1971", "mysql": "8.4.0"}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def archive_members(path):
    """Validate every entry before writing any data; reject parent conflicts."""
    result, seen = [], {}
    with tarfile.open(path, "r:gz") as archive:
        for m in archive:
            raw = m.name
            p = PurePosixPath(raw)
            if p.is_absolute() or ".." in p.parts or "\\" in raw or "\x00" in raw:
                raise ValueError("Unsafe archive path")
            name = str(p)
            if (name in ("", ".") and not m.isdir()) or not (m.isfile() or m.isdir()):
                raise ValueError("Links and special archive entries need manual review")
            if name in seen:
                raise ValueError("Duplicate archive path")
            seen[name] = "dir" if m.isdir() else "file"
            result.append(m)
    for name, kind in seen.items():
        if any(seen.get(str(parent)) == "file" for parent in PurePosixPath(name).parents):
            raise ValueError("Archive file/parent conflict")
    return result

def verify(bundle):
    bundle = Path(bundle).resolve(strict=True)
    manifest_file = bundle / "manifest.json"
    if manifest_file.is_symlink():
        raise ValueError("Manifest must be a regular local file")
    manifest = json.loads(manifest_file.read_text())
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported manifest schema")
    if manifest.get("versions") != BASELINE:
        raise ValueError("Unsupported version pair: rehearse a same-version restore first")
    if not manifest.get("capture_id") or not manifest.get("consistency_evidence"):
        raise ValueError("Capture identity and consistency evidence are required")
    if manifest.get("databases") != ["onlyoffice", "onlyoffice_mailserver"]:
        raise ValueError("This baseline requires both application and mail-server databases")
    entries = manifest.get("artifacts", {})
    if set(entries) != set(REQUIRED):
        raise ValueError("The complete required backup artifact set is missing")
    unpacked = 0
    for name, destination in REQUIRED.items():
        f = bundle / name
        expected = entries[name]
        if f.is_symlink() or not f.is_file():
            raise ValueError("Artifact missing or is a link: " + name)
        if not re.fullmatch(r"[0-9a-f]{64}", expected.get("sha256", "")):
            raise ValueError("Invalid checksum: " + name)
        if f.stat().st_size != expected.get("bytes") or digest(f) != expected["sha256"]:
            raise ValueError("Checksum/size mismatch: " + name)
        if f.stat().st_size == 0:
            raise ValueError("Empty backup artifact: " + name)
        if destination:
            members = archive_members(f)
            unpacked += sum(m.size for m in members if m.isfile())
            if name == "community-data.tar.gz":
                keys = [m for m in members if str(PurePosixPath(m.name)) == ".private/machinekey" and m.isfile() and m.size > 0]
                if len(keys) != 1:
                    raise ValueError("Original CommunityServer machine key is missing")
    return manifest, unpacked

def unpack(bundle, target, preserve_owner=True):
    bundle = Path(bundle).resolve(strict=True)
    manifest, size = verify(bundle)
    target = Path(target)
    # Reject all linked path components, even links pointing within the lab.
    if any(p.is_symlink() for p in [target, *target.parents]):
        raise ValueError("Restore target cannot contain symlinks")
    if target.exists():
        raise ValueError("Restore target must not exist; overwrites are forbidden")
    parent = target.parent.resolve(strict=True)
    if (parent / ".workspace-mail-lab").is_symlink() or not (parent / ".workspace-mail-lab").is_file():
        raise ValueError("Parent must be an initialized dedicated lab directory")
    required = size + (bundle / "database.sql").stat().st_size
    if shutil.disk_usage(parent).free < required * 1.2:
        raise ValueError("Insufficient free space including 20% extraction headroom")
    # Verification completed before the destination is created.
    target.mkdir(mode=0o700)
    try:
        shutil.copyfile(bundle / "database.sql", target / "database.sql")
        os.chmod(target / "database.sql", 0o600)
        for name, destination in REQUIRED.items():
            if not destination:
                continue
            root = target / destination
            # Parent lab directory is private; bind-mounted app data must be
            # traversable by service users. A tar root entry restores its mode.
            root.mkdir(mode=0o755)
            with tarfile.open(bundle / name, "r:gz") as archive:
                members = archive_members(bundle / name)
                directories = []
                for m in members:
                    p = root / str(PurePosixPath(m.name))
                    if m.isdir():
                        p.mkdir(parents=True, exist_ok=True)
                        directories.append((p, m))
                        continue
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(m) as source, p.open("xb") as dest:
                        shutil.copyfileobj(source, dest, 1024 * 1024)
                    if preserve_owner:
                        os.chown(p, m.uid, m.gid)
                    os.chmod(p, m.mode & 0o777)
                    os.utime(p, (m.mtime, m.mtime))
                for p, m in reversed(directories):
                    if preserve_owner:
                        os.chown(p, m.uid, m.gid)
                    os.chmod(p, m.mode & 0o777)
                    os.utime(p, (m.mtime, m.mtime))
        receipt = {"capture_id": manifest["capture_id"], "manifest_sha256": digest(bundle / "manifest.json"),
                   "state": "unpacked-only; database not imported; application not started", "versions": manifest["versions"]}
        (target / "restore-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        return receipt
    except Exception:
        # A failed attempt remains intact for diagnosis. Never remove it.
        (target / "RESTORE-INCOMPLETE").touch()
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle", type=Path)
    p.add_argument("--target", type=Path)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    try:
        manifest, size = verify(a.bundle)
        print(json.dumps({"capture_id": manifest["capture_id"], "archive_bytes_unpacked": size,
                          "result": "checksums and archive paths verified", "restore_tested": False}))
        if a.apply:
            if not a.target:
                p.error("--target is required with --apply")
            if os.name != "posix" or os.uname().sysname != "Linux" or os.geteuid() != 0:
                p.error("Apply requires root on the dedicated Linux lab to preserve ownership")
            print(json.dumps(unpack(a.bundle, a.target)))
        else:
            print("Verification only. Nothing was written.")
    except (ValueError, OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        p.exit(1, str(exc) + "\n")

if __name__ == "__main__":
    main()
