"""Helper to launch KoboldCPP engines for Requiem.


This script spawns the primary KoboldCPP model along with optional
smaller models used for intent classification and planning. All models
are launched on CUDA via the `koboldcpp` command.

This script spawns one primary KoboldCPP process and, optionally, a
secondary process used for emotional hinting. It expects the `koboldcpp`
command to be available in the environment.

"""

from __future__ import annotations

import os
import subprocess


def launch(model: str, port: int) -> subprocess.Popen:
    cmd = [
        "koboldcpp",
        "--model",
        model,
        "--port",
        str(port),
        "--usecublas",
    ]
    return subprocess.Popen(cmd)


def main() -> None:
    model = os.getenv("MAIN_MODEL", "Qwen2.5-14B-Instruct-Q5_K_M.gguf")
    port = int(os.getenv("KOBOLD_PORT", "5001"))

    intent_model = os.getenv("INTENT_MODEL")
    intent_port = int(os.getenv("INTENT_PORT", "5002"))
    planner_model = os.getenv("THOUGHTS_MODEL")
    planner_port = int(os.getenv("THOUGHTS_PORT", "5003"))

    procs = [launch(model, port)]
    if intent_model:
        procs.append(launch(intent_model, intent_port))
    if planner_model:
        procs.append(launch(planner_model, planner_port))
    assist_model = os.getenv("ASSIST_MODEL")
    assist_port = int(os.getenv("ASSIST_PORT", "5002"))

    procs = [launch(model, port)]
    if assist_model:
        procs.append(launch(assist_model, assist_port))

    for p in procs:
        p.wait()


if __name__ == "__main__":
    main()

