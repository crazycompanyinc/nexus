#!/usr/bin/env python3
"""
ROTA TRON Integration for Nexus Videojuego / ONEIROS
Archivo que se incluye en el proyecto Nexus para que avise a ROTATRON cuando termina.
"""

import subprocess
import sys
from pathlib import Path

ROTATRON_NOTIFY = Path("/root/.hermes/skills/rotatron/scripts/rotatron_notify.py")


def notify_nexus_game_complete(output: str, metadata: dict = None):
    """Avisar a ROTATRON que Nexus Videojuego terminó una tarea."""
    if not ROTATRON_NOTIFY.exists():
        print("[ROTA TRON] Notify script not found, skipping")
        return

    cmd = [
        sys.executable, str(ROTATRON_NOTIFY),
        "notify",
        "--agent", "nexus_videojuego",
        "--project", "nexus_videojuego",
        "--type", "task_complete",
        "--output", output,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(f"[ROTA TRON] Notificado: {result.stdout.strip()}")
    except Exception as e:
        print(f"[ROTA TRON] Error notifying: {e}")


def get_next_nexus_game_prompt() -> str:
    """Obtener el siguiente prompt de ROTATRON para Nexus Videojuego."""
    if not ROTATRON_NOTIFY.exists():
        return ""

    try:
        result = subprocess.run(
            [sys.executable, str(ROTATRON_NOTIFY), "prompt", "--project", "nexus_videojuego"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip()
    except Exception:
        return ""


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        notify_nexus_game_complete("Test notification from Nexus Videojuego")
        prompt = get_next_nexus_game_prompt()
        print(f"Next prompt: {prompt[:200] if prompt else 'None'}")
