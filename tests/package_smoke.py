from __future__ import annotations

import argparse
import json
import os
import subprocess
import tarfile
import tempfile
import textwrap
import venv
import zipfile
from pathlib import Path

_FORBIDDEN_ARCHIVE_MEMBERS = {
    "lint_output.txt",
    "typecheck_output.txt",
    "test_output.txt",
    "smoke_output.json",
}

_REQUIRED_LICENSE_BASENAMES = {"LICENSE", "NOTICE"}
_REQUIRED_SCHEMA_BASENAMES = {
    "asset-spec.schema.json",
    "common-request.schema.json",
    "common-result.schema.json",
    "export-record.schema.json",
    "operation-log.schema.json",
    "part-spec.schema.json",
    "qa-report.schema.json",
    "scene-spec.schema.json",
    "snapshot-metadata.schema.json",
    "world-spec.schema.json",
}


def _find_distribution(dist_dir: Path, pattern: str, label: str) -> Path:
    distributions = sorted(dist_dir.glob(pattern))
    if not distributions:
        raise FileNotFoundError(f"No blender-mcp {label} found under {dist_dir}")
    return distributions[-1]


def _default_artifacts(dist_dir: Path) -> list[Path]:
    return [
        _find_distribution(dist_dir, "blender_mcp-*.whl", "wheel"),
        _find_distribution(dist_dir, "blender_mcp-*.tar.gz", "sdist"),
    ]


def _artifact_label(artifact_path: Path) -> str:
    if artifact_path.suffix == ".whl":
        return "wheel"
    if artifact_path.name.endswith(".tar.gz"):
        return "sdist"
    raise ValueError(f"Unsupported distribution artifact: {artifact_path}")


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _isolated_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("BLENDER_MCP_REPO_ROOT", None)
    return env


def _archive_members(artifact_path: Path) -> list[str]:
    if artifact_path.suffix == ".whl":
        with zipfile.ZipFile(artifact_path) as archive:
            return archive.namelist()
    if artifact_path.name.endswith(".tar.gz"):
        with tarfile.open(artifact_path, "r:gz") as archive:
            return [member.name for member in archive.getmembers() if member.isfile()]
    raise ValueError(f"Unsupported distribution artifact: {artifact_path}")


def _assert_archive_hygiene(artifact_path: Path, *, label: str) -> None:
    leaked_members: list[str] = []
    for member in _archive_members(artifact_path):
        if Path(member).name in _FORBIDDEN_ARCHIVE_MEMBERS:
            leaked_members.append(member)
    if leaked_members:
        raise RuntimeError(
            f"{label} archive contains forbidden validation artifacts: {sorted(leaked_members)}"
        )


def _assert_archive_license_files(artifact_path: Path, *, label: str) -> None:
    basenames = {Path(member).name for member in _archive_members(artifact_path)}
    missing = sorted(_REQUIRED_LICENSE_BASENAMES - basenames)
    if missing:
        raise RuntimeError(f"{label} archive is missing required license files: {missing}")


def _assert_archive_schemas(artifact_path: Path, *, label: str) -> None:
    basenames = {Path(member).name for member in _archive_members(artifact_path)}
    missing = sorted(_REQUIRED_SCHEMA_BASENAMES - basenames)
    if missing:
        raise RuntimeError(f"{label} archive is missing published schemas: {missing}")


def _metadata_text(artifact_path: Path) -> str:
    if artifact_path.suffix == ".whl":
        with zipfile.ZipFile(artifact_path) as archive:
            metadata_name = next(
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            )
            return archive.read(metadata_name).decode("utf-8")
    if artifact_path.name.endswith(".tar.gz"):
        with tarfile.open(artifact_path, "r:gz") as archive:
            metadata_member = next(
                member for member in archive.getmembers() if member.isfile() and member.name.endswith("/PKG-INFO")
            )
            extracted = archive.extractfile(metadata_member)
            if extracted is None:
                raise RuntimeError(f"Unable to read PKG-INFO from {artifact_path}")
            return extracted.read().decode("utf-8")
    raise ValueError(f"Unsupported distribution artifact: {artifact_path}")


def _assert_metadata_license(artifact_path: Path, *, label: str) -> None:
    metadata = _metadata_text(artifact_path)
    if "Proprietary" in metadata:
        raise RuntimeError(f"{label} metadata still advertises a proprietary license")
    expected_markers = (
        "License-Expression: Apache-2.0",
        "License: Apache-2.0",
        "License :: OSI Approved :: Apache Software License",
    )
    if not any(marker in metadata for marker in expected_markers):
        raise RuntimeError(f"{label} metadata does not advertise Apache-2.0 licensing")


def _smoke_script() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations

        import asyncio
        import json
        import socket
        import sqlite3
        from pathlib import Path

        from mcp_server.config import ServerSettings
        from mcp_server.server import MCPServerApplication


        def find_free_port() -> int:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                return int(sock.getsockname()[1])


        async def smoke() -> None:
            base_dir = Path.cwd()
            env = {
                "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
                "BLENDER_MCP_CONTROLLER_MODE": "mock",
                "BLENDER_MCP_CONTROLLER_PORT": str(find_free_port()),
                "BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS": "5",
            }
            settings = ServerSettings.from_env(env, base_dir=base_dir)
            app = MCPServerApplication(settings)
            try:
                initialize_payload = await app.initialize()
                await app.start()
                runtime = await app.context.bridge.get_runtime_info()
                db_path = settings.metadata_db_path()
                with sqlite3.connect(db_path) as connection:
                    row = connection.execute(
                        "SELECT version_num FROM alembic_version"
                    ).fetchone()
                print(
                    json.dumps(
                        {
                            "cwd": str(base_dir),
                            "repo_root": str(settings.repo_root),
                            "db_path": str(db_path),
                            "db_revision": row[0] if row else None,
                            "protocol_version": initialize_payload["protocolVersion"],
                            "runtime_backend": runtime["backend"],
                        },
                        sort_keys=True,
                    )
                )
            finally:
                await app.stop()


        asyncio.run(smoke())
        """
    )


def _validate_artifact(artifact_path: Path, *, label: str, temp_root: Path) -> dict[str, object]:
    _assert_archive_hygiene(artifact_path, label=label)
    _assert_archive_license_files(artifact_path, label=label)
    _assert_archive_schemas(artifact_path, label=label)
    _assert_metadata_license(artifact_path, label=label)
    install_root = temp_root / label
    install_root.mkdir(parents=True, exist_ok=True)
    venv_dir = install_root / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    python_executable = _venv_python(venv_dir)
    env = _isolated_env()

    _run([str(python_executable), "-m", "pip", "install", str(artifact_path)], cwd=install_root, env=env)

    run_dir = install_root / "isolated-run"
    run_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(python_executable), "-c", _smoke_script()],
        cwd=run_dir,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    if payload["runtime_backend"] != "mock":
        raise RuntimeError(f"Expected mock runtime backend, got {payload['runtime_backend']}")
    if payload["protocol_version"] != "2024-11-05":
        raise RuntimeError(
            f"Unexpected protocol version from installed {label}: {payload['protocol_version']}"
        )
    if payload["db_revision"] != "0001_initial":
        raise RuntimeError(f"Unexpected alembic revision from installed {label}: {payload['db_revision']}")
    payload["artifact"] = label
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install built distribution artifacts into isolated venvs and smoke-test startup."
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        action="append",
        default=None,
        help="Optional explicit distribution artifact path to validate. Repeat to validate multiple artifacts.",
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        default=None,
        help="Optional explicit path to a wheel to validate. Deprecated alias for --artifact.",
    )
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"), help="Directory to search when --wheel is omitted.")
    args = parser.parse_args()

    if args.wheel is not None and args.artifact:
        parser.error("Use either --wheel or --artifact, not both.")

    artifact_paths = args.artifact or ([args.wheel] if args.wheel is not None else _default_artifacts(args.dist_dir))
    with tempfile.TemporaryDirectory(prefix="blender-mcp-package-check-") as temp_dir:
        temp_root = Path(temp_dir)
        payloads = [
            _validate_artifact(artifact_path.resolve(), label=_artifact_label(artifact_path), temp_root=temp_root)
            for artifact_path in artifact_paths
        ]
        print(json.dumps(payloads, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())