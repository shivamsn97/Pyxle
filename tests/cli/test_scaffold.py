from pathlib import Path

import pytest

from pyxle.cli.scaffold import (
    FilesystemWriter,
    InvalidProjectName,
    slugify_project_name,
    validate_project_name,
)


def test_slugify_and_validate_happy_path():
    assert slugify_project_name("My Awesome_App") == "my-awesome-app"
    assert validate_project_name("My Awesome_App") == "my-awesome-app"


@pytest.mark.parametrize("value", ["", " ", "!!!", "..", "-demo", ".hidden"])
def test_slugify_rejects_invalid_names(value: str) -> None:
    with pytest.raises(InvalidProjectName):
        validate_project_name(value)


def test_filesystem_writer_handles_text_and_binary(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    writer = FilesystemWriter(root)
    writer.ensure_root()

    with pytest.raises(FileExistsError):
        writer.ensure_root()

    writer.write("hello.txt", "hello world")
    writer.write("nested/data.bin", b"\x00\x01", binary=True)
    with pytest.raises(FileExistsError):
        writer.write("hello.txt", "again")
    writer.touch_directory("pages/api")

    assert (root / "hello.txt").read_text(encoding="utf-8") == "hello world"
    assert (root / "nested/data.bin").read_bytes() == b"\x00\x01"
    assert (root / "pages/api").is_dir()

    # Simulate force overwrite when a file exists at the target path.
    root.touch()
    writer = FilesystemWriter(root)
    writer.ensure_root(force=True)
    assert root.is_dir()

    # Force overwrite when a directory already exists.
    (root / "placeholder.txt").write_text("data", encoding="utf-8")
    writer.ensure_root(force=True)
    assert not (root / "placeholder.txt").exists()
