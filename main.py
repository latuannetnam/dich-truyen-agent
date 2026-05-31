from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dich_truyen_agent.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
