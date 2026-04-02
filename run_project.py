import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    script = root / "start-demo.ps1"

    if not script.exists():
        print(f"start-demo.ps1 not found at: {script}")
        return 1

    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]

    print("Starting full project stack...")
    print(f"Project root: {root}")

    try:
        result = subprocess.run(command, cwd=str(root), check=False)
        return int(result.returncode)
    except Exception as error:
        print(f"Failed to start project: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
