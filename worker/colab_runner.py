"""Orchestrate Colab CLI sessions for batch inference."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SESSION_NAME_DEFAULT = "jobtrack"
INFER_SCRIPT = Path(__file__).with_name("infer_colab.py")
REMOTE_BATCH = "/content/batch.json"
REMOTE_INFER = "/content/infer_colab.py"
EXEC_TIMEOUT_SECONDS = 1800


class ColabError(RuntimeError):
    pass


def _run(
    cmd: list[str],
    *,
    timeout: Optional[int] = None,
    stdin_text: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        input=stdin_text,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def stop_session(session_name: str = SESSION_NAME_DEFAULT) -> None:
    result = _run(["colab", "stop", "-s", session_name], timeout=120)
    if result.returncode != 0:
        logger.warning(
            "colab stop failed (may already be gone): %s %s",
            result.stdout,
            result.stderr,
        )


def cleanup_orphans(session_name: str = SESSION_NAME_DEFAULT) -> None:
    result = _run(["colab", "sessions"], timeout=60)
    output = (result.stdout or "") + (result.stderr or "")
    if session_name in output:
        logger.warning("Found leftover Colab session %s; stopping", session_name)
        stop_session(session_name)


def run_inference_batch(
    messages: list[dict[str, str]],
    *,
    session_name: str = SESSION_NAME_DEFAULT,
) -> list[dict[str, Any]]:
    """Start T4 session, mount Drive, exec infer script, stop, return JSON list."""
    if not messages:
        return []
    if not INFER_SCRIPT.exists():
        raise ColabError(f"Missing infer script: {INFER_SCRIPT}")

    cleanup_orphans(session_name)

    with tempfile.TemporaryDirectory(prefix="jobtrack-") as tmp:
        batch_path = Path(tmp) / "batch.json"
        batch_path.write_text(
            json.dumps({"messages": messages}, ensure_ascii=True),
            encoding="utf-8",
        )

        started = False
        try:
            new = _run(
                ["colab", "new", "-s", session_name, "--gpu", "T4"],
                timeout=300,
            )
            if new.returncode != 0:
                raise ColabError(f"colab new failed: {new.stdout}\n{new.stderr}")
            started = True

            mount = _run(
                ["colab", "drivemount", "-s", session_name],
                timeout=600,
            )
            if mount.returncode != 0:
                raise ColabError(
                    f"colab drivemount failed: {mount.stdout}\n{mount.stderr}"
                )

            upload_batch = _run(
                [
                    "colab",
                    "upload",
                    "-s",
                    session_name,
                    str(batch_path),
                    REMOTE_BATCH,
                ],
                timeout=120,
            )
            if upload_batch.returncode != 0:
                raise ColabError(
                    "colab upload batch failed: "
                    f"{upload_batch.stdout}\n{upload_batch.stderr}"
                )

            upload_script = _run(
                [
                    "colab",
                    "upload",
                    "-s",
                    session_name,
                    str(INFER_SCRIPT),
                    REMOTE_INFER,
                ],
                timeout=120,
            )
            if upload_script.returncode != 0:
                raise ColabError(
                    "colab upload infer script failed: "
                    f"{upload_script.stdout}\n{upload_script.stderr}"
                )

            # Run the uploaded script with argv so it can find the batch file.
            exec_cmd = (
                "import runpy, sys\n"
                f"sys.argv = [{REMOTE_INFER!r}, {REMOTE_BATCH!r}]\n"
                f"runpy.run_path({REMOTE_INFER!r}, run_name='__main__')\n"
            )
            exec_result = _run(
                [
                    "colab",
                    "exec",
                    "-s",
                    session_name,
                    "--timeout",
                    str(EXEC_TIMEOUT_SECONDS),
                ],
                timeout=EXEC_TIMEOUT_SECONDS + 120,
                stdin_text=exec_cmd,
            )
            if exec_result.returncode != 0:
                raise ColabError(
                    f"colab exec failed: {exec_result.stdout}\n{exec_result.stderr}"
                )

            return _parse_json_output(exec_result.stdout)
        finally:
            if started:
                stop_session(session_name)


def _parse_json_output(stdout: str) -> list[dict[str, Any]]:
    """Extract the JSON array printed by infer_colab.py from mixed stdout."""
    text = (stdout or "").strip()
    if not text:
        raise ColabError("Empty Colab stdout; expected JSON array")

    candidates = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(candidates):
        if line.startswith("["):
            try:
                data = json.loads(line)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue

    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return data
        except json.JSONDecodeError as exc:
            raise ColabError(f"Failed to parse Colab JSON: {exc}") from exc

    raise ColabError(f"No JSON array found in Colab output:\n{text[:2000]}")
