#!/usr/bin/env python3
"""Guarded, vendor-neutral project devflows."""
from __future__ import annotations
import argparse, shutil, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; PROTECTED={"main","master","staging","production"}
VENV_PYTHON=ROOT/".venv"/("Scripts/python.exe" if sys.platform=="win32" else "bin/python")
def run(*cmd: str) -> None: print("+", " ".join(cmd)); subprocess.run(cmd,cwd=ROOT,check=True)
def branch() -> str: return subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()
def check(kind: str) -> None:
    python=str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    if kind=="test": run(python,"-m","pytest")
    elif kind=="lint": run(python,"-m","compileall","-q","src","tests")
    else: print("GAP: no static type checker is configured")
def verify() -> None: check("lint"); check("test"); run("git","diff","--check")
def feature() -> str:
    value=branch()
    if not value or value in PROTECTED: raise SystemExit("Refusing delivery from a protected or detached branch")
    return value
def commit(message: str, paths: list[str]) -> None:
    feature(); verify()
    if not paths: raise SystemExit("Commit requires explicit paths")
    run("git","add","--",*paths)
    if not shutil.which("gitleaks"): raise SystemExit("gitleaks is required before commit (fail closed)")
    run("gitleaks","git","--staged","--redact"); run("git","commit","-m",message)
def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("action",choices=["verify","lint","test","typecheck","commit","push","pr","deploy-staging","deploy-production","rollback"]); p.add_argument("--message"); p.add_argument("--title"); p.add_argument("paths",nargs="*"); a=p.parse_args()
    if a.action=="verify": verify()
    elif a.action in {"lint","test","typecheck"}: check(a.action)
    elif a.action=="commit": commit(a.message or "",a.paths)
    elif a.action=="push": run("git","push","-u","origin",feature())
    elif a.action=="pr": feature(); run("gh","pr","create","--draft","--title",a.title or "Draft change","--fill")
    else: raise SystemExit(f"{a.action} is approval-gated and intentionally blocked")
if __name__=="__main__": main()
