"""Start all 4 agents together (each in its own process, output prefixed)."""
import subprocess
import sys
import threading

MODULES = ["planner_agent", "price_agent", "order_agent", "manager_agent"]


def pump(name, proc):
    for line in proc.stdout:
        print(f"[{name:<14}] {line}", end="")


def main():
    procs = []
    for m in MODULES:
        p = subprocess.Popen(
            [sys.executable, "-m", f"agents.{m}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        procs.append(p)
        threading.Thread(target=pump, args=(m, p), daemon=True).start()
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nStopping agents...")
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
