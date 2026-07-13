"""Copy an ignored local env profile to an approved NUC path without logging values."""
from __future__ import annotations
import argparse, re, subprocess
from pathlib import Path, PurePosixPath
ROOT=Path(__file__).resolve().parents[1]; HOSTS={"soma-nuc","odb-nuc","onno@192.168.1.228","onno@192.168.1.93"}
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("profile"); p.add_argument("host"); p.add_argument("remote_path"); p.add_argument("--confirm",action="store_true"); p.add_argument("--onno-approval-id"); a=p.parse_args()
    if not a.confirm or not re.fullmatch(r"[a-z0-9_-]+",a.profile) or a.host not in HOSTS: raise SystemExit("BLOCKED: confirmation, valid profile, and approved host required")
    path=PurePosixPath(a.remote_path)
    if not path.is_absolute() or path.name!=".env" or path.parts[:3]!=("/","home","onno") or any(not re.fullmatch(r"[A-Za-z0-9._-]+",x) for x in path.parts[3:-1]): raise SystemExit("BLOCKED: invalid destination")
    if a.profile=="production" and not (a.onno_approval_id or "").strip(): raise SystemExit("BLOCKED: production sync requires --onno-approval-id")
    source=ROOT/f".env.{a.profile}.local"
    if not source.is_file() or subprocess.run(["git","check-ignore","--quiet","--",source.name],cwd=ROOT).returncode: raise SystemExit("BLOCKED: profile missing or not ignored")
    print(f"syncing {source.name} to approved host/path (values hidden)"); subprocess.run(["scp","-q",str(source),f"{a.host}:{a.remote_path}"],check=True); subprocess.run(["ssh",a.host,"chmod","600",a.remote_path],check=True); print("environment profile synced; no values were logged"); return 0
if __name__=="__main__": raise SystemExit(main())
