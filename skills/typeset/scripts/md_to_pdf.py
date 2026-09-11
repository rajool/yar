#!/usr/bin/env python3
"""Compatibility entry point: the CLI is typeset.py since 4.0. Kept so callers
that still invoke md_to_pdf.py keep working."""
import sys

from typeset import main

if __name__ == "__main__":
    sys.exit(main())
