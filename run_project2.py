import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


CLOUDFLARE_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def run_command(command: list[str], cwd: Path | None = None) -> int:
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    return int(result.returncode)


def wait_for_http(url: str, attempts: int = 30, delay_seconds: float = 1.0) -> bool:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(delay_seconds)
    return False


def pids_on_port(port: int) -> list[int]:
    try:
        output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="ignore")
    except Exception:
        return []

    found: set[int] = set()
    marker = f":{port}"
    for line in output.splitlines():
        row = line.strip()
        if "LISTENING" not in row or marker not in row:
            continue
        parts = row.split()
        if not parts:
            continue
        try:
            found.add(int(parts[-1]))
        except ValueError:
            continue
    return sorted(found)


def kill_processes_on_port(port: int, label: str) -> None:
    for pid in pids_on_port(port):
        try:
            print(f"Stopping stale {label} process on port {port} (PID {pid})...")
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def resolve_cloudflared_path() -> str | None:
    direct = shutil.which("cloudflared")
    if direct:
        return direct

    candidates = [
        Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
        Path(os.getenv("ProgramFiles", "")) / "Cloudflare" / "Cloudflared" / "cloudflared.exe",
        Path(os.getenv("ProgramFiles", "")) / "cloudflared" / "cloudflared.exe",
        Path(os.getenv("ProgramFiles(x86)", "")) / "cloudflared" / "cloudflared.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def start_cloudflare_tunnel(cloudflared: str, target_url: str, label: str, timeout_seconds: int = 45) -> tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", target_url, "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    discovered = {"url": ""}

    def reader() -> None:
        if not proc.stdout:
            return
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            match = CLOUDFLARE_URL_PATTERN.search(line)
            if match and not discovered["url"]:
                discovered["url"] = match.group(0)
            # Keep logs concise but visible for diagnostics.
            print(f"[{label}] {line}")

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    end_at = time.time() + timeout_seconds
    while time.time() < end_at:
        if proc.poll() is not None:
            raise RuntimeError(f"cloudflared for {label} exited early with code {proc.returncode}")
        if discovered["url"]:
            return proc, discovered["url"]
        time.sleep(0.25)

    proc.terminate()
    raise RuntimeError(f"Timed out waiting for {label} tunnel URL")


def frontend_command(root: Path) -> list[str]:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js was not found in PATH.")
    vite = root / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.exists():
        raise RuntimeError("Vite is not installed. Run npm install in frontend first.")
    return [node, str(vite), "--host", "127.0.0.1", "--port", "5173"]


def make_temp_extension_bundle(root: Path, frontend_public_url: str, backend_public_url: str) -> Path:
    source_dir = root / "browser-extension" / "website-monitor-extension"
    if not source_dir.exists():
        raise RuntimeError("Extension source folder not found.")

    temp_root = root / ".temp_tunnel_extension"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    shutil.copytree(source_dir, temp_root)

    manifest_path = temp_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    frontend_pattern = frontend_public_url.rstrip("/") + "/*"
    backend_pattern = backend_public_url.rstrip("/") + "/*"

    host_permissions = list(manifest.get("host_permissions", []))
    for pattern in [frontend_pattern, backend_pattern]:
        if pattern not in host_permissions:
            host_permissions.append(pattern)
    manifest["host_permissions"] = host_permissions

    content_scripts = list(manifest.get("content_scripts", []))
    for item in content_scripts:
        matches = list(item.get("matches", []))
        if frontend_pattern not in matches:
            matches.append(frontend_pattern)
        item["matches"] = matches
    manifest["content_scripts"] = content_scripts

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return temp_root


def create_extension_zip(root: Path, extension_dir: Path) -> Path:
    zip_base = root / "tunnel-extension-package"
    zip_file = root / "tunnel-extension-package.zip"

    if zip_file.exists():
        zip_file.unlink()

    # make_archive expects a base name without extension.
    shutil.make_archive(str(zip_base), "zip", root_dir=str(extension_dir.parent), base_dir=extension_dir.name)
    return zip_file


def stop_demo_stack(root: Path) -> None:
    stop_script = root / "stop-demo.ps1"
    if not stop_script.exists():
        return
    run_command(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(stop_script),
        ],
        cwd=root,
    )


def main() -> int:
    root = Path(__file__).resolve().parent
    start_script = root / "start-demo.ps1"

    if not start_script.exists():
        print(f"start-demo.ps1 not found at: {start_script}")
        return 1

    cloudflared = resolve_cloudflared_path()
    if not cloudflared:
        print("cloudflared not found. Install it first (winget install Cloudflare.cloudflared).")
        return 1

    print("Launching local stack with existing script...")
    rc = run_command(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(start_script)],
        cwd=root,
    )
    if rc != 0:
        print("start-demo.ps1 failed.")
        return rc

    print("Checking backend health...")
    if not wait_for_http("http://127.0.0.1:8000/health", attempts=35, delay_seconds=1.0):
        print("Backend is not healthy on http://127.0.0.1:8000")
        return 1

    frontend_tunnel_proc: subprocess.Popen | None = None

    try:
        # Restart frontend in single-domain mode so remote browsers use /api through Vite proxy.
        kill_processes_on_port(5173, "frontend")
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = "/api"

        print("Starting frontend with tunneled backend URL...")
        frontend_proc = subprocess.Popen(
            frontend_command(root),
            cwd=str(root / "frontend"),
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not wait_for_http("http://127.0.0.1:5173", attempts=45, delay_seconds=1.0):
            print("Frontend failed to become ready on http://127.0.0.1:5173")
            frontend_proc.terminate()
            return 1

        print("Starting frontend Cloudflare tunnel...")
        frontend_tunnel_proc, frontend_public = start_cloudflare_tunnel(
            cloudflared, "http://127.0.0.1:5173", "frontend"
        )

        backend_public = frontend_public.rstrip("/") + "/api"

        ext_path = make_temp_extension_bundle(root, frontend_public, backend_public)
        ext_zip = create_extension_zip(root, ext_path)

        print("\n=== Public Tunnel Ready (Cloudflare) ===")
        print(f"Frontend URL (share this): {frontend_public}")
        print(f"Backend URL (via frontend proxy): {backend_public}")
        print("\nLoad this temporary extension folder in remote browser:")
        print(ext_path)
        print("Or send this zip to remote laptop and extract it before Load unpacked:")
        print(ext_zip)
        print("\nWhen you close this script (Ctrl+C), links stop working.")

        def handle_exit(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handle_exit)

        while True:
            if frontend_proc.poll() is not None:
                print("Frontend process exited. Stopping...")
                break
            if frontend_tunnel_proc.poll() is not None:
                print("Frontend tunnel exited. Stopping...")
                break
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping Cloudflare tunnel run...")
    except Exception as error:
        print(f"Failed to run Cloudflare tunnel mode: {error}")
        return 1
    finally:
        try:
            kill_processes_on_port(5173, "frontend")
        except Exception:
            pass
        for proc in [frontend_tunnel_proc]:
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        stop_demo_stack(root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
