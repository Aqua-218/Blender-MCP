from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mcp_server.config import ServerSettings
from mcp_server.utils import slugify


class WorkspaceViolationError(ValueError):
    pass


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ProjectPaths:
    workspace_root: Path
    project_dir: Path
    blend_file_path: Path
    render_dir: Path
    export_dir: Path
    snapshot_dir: Path


class WorkspaceManager:
    def __init__(self, settings: ServerSettings):
        self.settings = settings

    def bootstrap(self) -> None:
        self.settings.ensure_workspace_directories()

    def _resolve_rooted_path(self, candidate: str | Path) -> Path:
        raw = Path(candidate)
        if raw.is_absolute():
            return raw
        parts = raw.parts
        if parts:
            root_name = parts[0]
            for root in self.settings.workspace_roots:
                if root.name == root_name:
                    remainder = Path(*parts[1:]) if len(parts) > 1 else Path()
                    return (root / remainder).resolve(strict=False)
        return (self.settings.workspace_roots[0] / raw).resolve(strict=False)

    def canonicalize_existing_path(self, candidate: str | Path, *, allowed_extensions: list[str]) -> Path:
        path = self._resolve_rooted_path(candidate)
        if not path.exists():
            raise WorkspaceViolationError(f"Path does not exist: {path}")
        resolved = path.resolve(strict=True)
        self._assert_allowed_root(resolved)
        self._assert_allowed_extension(resolved, allowed_extensions)
        return resolved

    def canonicalize_output_path(self, candidate: str | Path, *, allowed_extensions: list[str]) -> Path:
        path = self._resolve_rooted_path(candidate)
        resolved = path.resolve(strict=False)
        self._assert_allowed_root(resolved)
        self._assert_allowed_extension(resolved, allowed_extensions)
        return resolved

    def _assert_allowed_root(self, candidate: Path) -> None:
        resolved = candidate.resolve(strict=False)
        if not any(_is_relative_to(resolved, root.resolve()) for root in self.settings.workspace_roots):
            raise WorkspaceViolationError(f"Path is outside allowlisted roots: {resolved}")

    def owning_workspace_root(self, candidate: str | Path) -> Path:
        resolved = self._resolve_rooted_path(candidate).resolve(strict=False)
        for root in self.settings.workspace_roots:
            normalized_root = root.resolve()
            if _is_relative_to(resolved, normalized_root):
                return normalized_root
        raise WorkspaceViolationError(f"Path is outside allowlisted roots: {resolved}")

    @staticmethod
    def _assert_allowed_extension(candidate: Path, allowed_extensions: list[str]) -> None:
        if candidate.suffix.lower() not in {item.lower() for item in allowed_extensions}:
            raise WorkspaceViolationError(f"Unsupported extension for path: {candidate}")

    def choose_workspace_root(self, candidate: str | Path | None = None) -> Path:
        if candidate is None:
            return self.settings.workspace_roots[0]
        raw = Path(candidate)
        if not raw.is_absolute():
            normalized_candidate = raw.as_posix().strip("/")
            for root in self.settings.workspace_roots:
                if normalized_candidate == root.name:
                    return root.resolve()
        return self.owning_workspace_root(candidate)

    def plan_project_paths(self, project_id: str, project_name: str, workspace_root: Path | None = None) -> ProjectPaths:
        root = self.choose_workspace_root(workspace_root)
        safe_name = slugify(project_name)
        project_dir = root / self.settings.artifact_directories.projects / f"{safe_name}-{project_id}"
        render_dir = root / self.settings.artifact_directories.renders / project_id
        export_dir = root / self.settings.artifact_directories.exports / project_id
        snapshot_dir = root / self.settings.artifact_directories.snapshots / project_id
        blend_file_path = project_dir / f"{safe_name}.blend"
        return ProjectPaths(
            workspace_root=root,
            project_dir=project_dir,
            blend_file_path=blend_file_path,
            render_dir=render_dir,
            export_dir=export_dir,
            snapshot_dir=snapshot_dir,
        )

    def ensure_project_layout(self, project_paths: ProjectPaths) -> None:
        for path in (
            project_paths.project_dir,
            project_paths.render_dir,
            project_paths.export_dir,
            project_paths.snapshot_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
