import shutil
from pathlib import Path
from sphinx.cmd import build

if __name__ == '__main__':
    source_root = Path(__file__).parent
    build_root = source_root.parent / "build"
    try:
        shutil.rmtree(build_root)
    except FileNotFoundError:
        pass
    build.build_main([str(source_root), str(build_root)])
