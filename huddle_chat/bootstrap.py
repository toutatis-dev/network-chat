import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def get_venv_python(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run_command(cmd: list[str], quiet: bool = False) -> int:
    if quiet:
        return subprocess.run(
            cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
    return subprocess.run(cmd, check=False).returncode


def ensure_venv(base_dir: Path, requirements_file: Path) -> Path:
    venv_dir = base_dir / "venv"
    venv_python = get_venv_python(venv_dir)

    if not venv_dir.exists():
        print("[System] Creating virtual environment...")
        code = run_command([sys.executable, "-m", "venv", str(venv_dir)])
        if code != 0:
            raise RuntimeError("Failed to create virtual environment.")

    if run_command([str(venv_python), "--version"], quiet=True) != 0:
        print("[System] Detected broken virtual environment. Recreating...")
        shutil.rmtree(venv_dir, ignore_errors=True)
        code = run_command([sys.executable, "-m", "venv", str(venv_dir)])
        if code != 0:
            raise RuntimeError("Failed to recreate virtual environment.")

    imports_ok = (
        run_command(
            [
                str(venv_python),
                "-c",
                "import prompt_toolkit, portalocker, watchdog, dependency_injector, huddle_chat.ui",
            ],
            quiet=True,
        )
        == 0
    )
    if not imports_ok:
        print("[System] Installing/Updating dependencies...")
        run_command(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], True
        )
        code = run_command(
            [str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)]
        )
        if code != 0:
            raise RuntimeError("Failed to install dependencies.")

    return venv_python


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Only verify venv/dependencies; do not start the app.",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    requirements = (base_dir / args.requirements).resolve()
    chat_py = (base_dir / "chat.py").resolve()

    try:
        venv_python = ensure_venv(base_dir, requirements)
    except RuntimeError as exc:
        print(f"[Error] {exc}")
        return 1

    if args.preflight:
        print("[System] Preflight checks passed.")
        return 0

    print("[System] Starting Huddle Chat...")
    return run_command([str(venv_python), str(chat_py)])


if __name__ == "__main__":
    raise SystemExit(main())
