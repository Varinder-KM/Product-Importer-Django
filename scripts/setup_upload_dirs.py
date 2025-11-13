#!/usr/bin/env python
"""
Create required media directories for uploads.
"""
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    uploads_dir = base_dir / "media" / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ensured upload directory exists at: {uploads_dir}")


if __name__ == "__main__":
    main()

