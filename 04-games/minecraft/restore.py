import os
import sys
import json
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

def load_env(env_path: Path) -> dict:
    """Parses key-value pairs from a .env file."""
    env_vars = {}
    if not env_path.is_file():
        return env_vars
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip().strip("\"'")
    return env_vars

def run_compose_cmd(compose_dir: Path, cmd: list[str], capture: bool = False, env: dict = None) -> subprocess.CompletedProcess:
    """Runs a docker compose command scoped to the selected directory."""
    full_cmd = ["docker", "compose"] + cmd
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    
    result = subprocess.run(
        full_cmd,
        cwd=compose_dir,
        text=True,
        capture_output=capture,
        env=merged_env
    )
    if result.returncode != 0 and not capture:
        print(f"\n[ERROR] Command failed: {' '.join(full_cmd)}")
        if result.stderr:
            print(f"[STDERR] {result.stderr}")
    return result

def select_server_directory() -> Path:
    """Opens a Tkinter dialog to select the target server directory."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    
    selected_dir = filedialog.askdirectory(
        title="Select Minecraft Server Directory containing docker-compose.yml"
    )
    root.destroy()
    
    if not selected_dir:
        print("No directory selected. Aborting.")
        sys.exit(0)
        
    dir_path = Path(selected_dir).resolve()
    compose_file = dir_path / "docker-compose.yml"
    if not compose_file.exists():
        compose_file = dir_path / "compose.yaml"
        if not compose_file.exists():
            print(f"[ERROR] No docker-compose.yml found in: {dir_path}")
            sys.exit(1)
            
    return dir_path

def main():
    server_dir = select_server_directory()
    env_file = server_dir / ".env"
    
    print(f"Target directory: {server_dir}")
    
    local_env = load_env(env_file)
    if "RESTIC_PASSWORD" in local_env:
        print("Found RESTIC_PASSWORD in local .env.")
    else:
        print("Warning: RESTIC_PASSWORD not explicitly defined in .env. Falling back to container environment.")

    # 1. Discover active service names via docker compose
    ps_res = run_compose_cmd(server_dir, ["ps", "--format", "json"], capture=True, env=local_env)
    if ps_res.returncode != 0:
        print("[ERROR] Failed to query Docker Compose services. Is Docker running?")
        sys.exit(1)

    # 2. Stop the primary Minecraft server service
    print("\nStopping Minecraft server service...")
    # Targets standard service naming or stops all services except backup
    run_compose_cmd(server_dir, ["stop", "minecraft-server"], env=local_env)
    run_compose_cmd(server_dir, ["stop", "minecraft-bedrock-server"], env=local_env)

    # 3. Retrieve snapshots from the mc-backup service container
    print("Querying Restic snapshots via mc-backup service...")
    snap_res = run_compose_cmd(
        server_dir, 
        ["exec", "-T", "mc-backup", "restic", "snapshots", "--json"], 
        capture=True, 
        env=local_env
    )
    
    if snap_res.returncode != 0:
        print(f"[ERROR] Failed to retrieve snapshots:\n{snap_res.stderr}")
        print("Restarting server...")
        run_compose_cmd(server_dir, ["start"], env=local_env)
        sys.exit(1)

    try:
        snapshots = json.loads(snap_res.stdout)
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON returned by Restic:\n{snap_res.stdout}")
        sys.exit(1)

    if not snapshots:
        print("No Restic snapshots available to restore.")
        run_compose_cmd(server_dir, ["start"], env=local_env)
        sys.exit(0)

    # 4. Display snapshots in terminal
    print("\n================ Available Snapshots ================")
    for i, snap in enumerate(snapshots):
        short_id = snap.get("id", "")[:8]
        time_str = snap.get("time", "")[:19].replace("T", " ")
        tags = ", ".join(snap.get("tags", [])) if snap.get("tags") else "None"
        paths = ", ".join(snap.get("paths", []))
        print(f"[{i:2d}] ID: {short_id} | Time: {time_str} | Tags: {tags:<15} | Path: {paths}")
    print("=====================================================")

    selection = input("\nEnter the index number of the snapshot to restore (or 'q' to cancel): ").strip()
    if selection.lower() == "q":
        print("Restoration cancelled. Restarting services...")
        run_compose_cmd(server_dir, ["start"], env=local_env)
        sys.exit(0)

    try:
        idx = int(selection)
        selected_snapshot = snapshots[idx]
        target_snap_id = selected_snapshot["id"]
    except (ValueError, IndexError):
        print("[ERROR] Invalid selection index. Aborting.")
        run_compose_cmd(server_dir, ["start"], env=local_env)
        sys.exit(1)

    print(f"\nTargeting snapshot: {target_snap_id[:8]}")

    # 5. Create pre-restore safety snapshot
    print("\nCreating pre-restore safety snapshot with tag 'pre-restore'...")
    safety_res = run_compose_cmd(
        server_dir,
        ["exec", "-T", "mc-backup", "restic", "backup", "/data", "--tag", "pre-restore"],
        env=local_env
    )
    if safety_res.returncode != 0:
        print("[WARNING] Failed to create pre-restore snapshot. Proceeding with restore...")

    # 6. Execute restore
    print(f"\nRestoring snapshot {target_snap_id[:8]} to /data...")
    restore_res = run_compose_cmd(
        server_dir,
        ["exec", "-T", "mc-backup", "restic", "restore", target_snap_id, "--target", "/", "--overwrite", "always"],
        env=local_env
    )

    if restore_res.returncode != 0:
        print("[ERROR] Restic restore failed.")
        sys.exit(1)

    # 7. Restart services
    print("\nRestarting Minecraft server...")
    run_compose_cmd(server_dir, ["start"], env=local_env)
    print("Restore procedure completed successfully.")

if __name__ == "__main__":
    main()