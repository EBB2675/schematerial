"""Execute an extractor using an explicitly provisioned Python interpreter."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schematerial.extraction.contract import read_document


@dataclass(frozen=True)
class ExtractorEnvironment:
    name: str
    python: Path


class ExtractorError(RuntimeError):
    """An extractor could not be started or did not complete successfully."""


def run_extractor(
    environment: ExtractorEnvironment,
    script: Path,
    *,
    arguments: tuple[str, ...] = (),
    input_text: str = "",
    timeout: float = 60,
) -> dict[str, Any]:
    """Return validated JSON; stdout is the document, stderr is diagnostics.

    Isolated Python mode ignores PYTHONPATH and user-site packages. Provisioning
    the selected environment is external to the app; no automatic installation
    or fallback to the app interpreter takes place here.
    """
    python = environment.python.absolute()
    if not python.is_file():
        raise ExtractorError(
            f"Extractor environment {environment.name!r} is missing its interpreter: {python}"
        )
    script = script.absolute()
    if not script.is_file():
        raise ExtractorError(f"Extractor script does not exist: {script}")
    if timeout <= 0:
        raise ValueError("Extractor timeout must be positive")
    try:
        result = subprocess.run(
            [str(python), "-I", str(script), *arguments],
            input=input_text, capture_output=True, text=True, encoding="utf-8",
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ExtractorError(
            f"Extractor environment {environment.name!r}: timed out after {timeout}s"
        ) from error
    except OSError as error:
        raise ExtractorError(
            f"Extractor environment {environment.name!r}: cannot execute {python}: {error}"
        ) from error
    if result.returncode:
        raise ExtractorError(
            f"Extractor environment {environment.name!r}: exit {result.returncode}; "
            f"{result.stderr.strip()}"
        )
    return read_document(result.stdout)
