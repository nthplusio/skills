"""Write a reproducible archive with one enclosing package directory."""

from pathlib import Path
import sys
import zipfile


def archive(folder, output):
    folder = Path(folder)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for source in sorted(folder.rglob("*")):
            if source.is_symlink():
                raise ValueError(f"Symlink forbidden: {source}")
            if not source.is_file():
                continue
            info = zipfile.ZipInfo(source.relative_to(folder.parent).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (source.stat().st_mode & 0xFFFF) << 16
            target.writestr(info, source.read_bytes())


if __name__ == "__main__":
    archive(*sys.argv[1:])
