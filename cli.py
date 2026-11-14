#!/usr/bin/env python3
"""Top-level CLI shim: python cli.py check|demo|serve"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui_event_contract.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
