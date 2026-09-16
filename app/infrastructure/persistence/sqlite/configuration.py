from pathlib import Path


def sqlite_database_url(base_dir: Path) -> str:
    return f"sqlite:///{base_dir / 'instance' / 'knowlayer.db'}"
