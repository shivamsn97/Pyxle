from pathlib import Path

import pytest

from pyxle.cli.templates import ScaffoldingTemplate, TemplateRegistry


def test_scaffolding_template_renders_context():
    template = ScaffoldingTemplate("package.json")
    rendered = template.render({"package_name": "demo"}).decode("utf-8")
    assert '"name": "demo"' in rendered


def test_scaffolding_template_reads_binary_payload(tmp_path, monkeypatch):
    template = ScaffoldingTemplate("favicon.ico", binary=True)
    fake_file = tmp_path / "favicon.ico"
    fake_file.write_bytes(b"binary-data")

    class StubPackage:
        def joinpath(self, resource_path):
            assert resource_path == "favicon.ico"
            return fake_file

    monkeypatch.setattr("pyxle.cli.templates.resources.files", lambda package: StubPackage())

    data = template.render()

    assert data == b"binary-data"


def test_template_registry_prevents_duplicates():
    registry = TemplateRegistry()
    registry.register("package.json", ScaffoldingTemplate("package.json"))
    with pytest.raises(ValueError):
        registry.register("package.json", ScaffoldingTemplate("package.json"))


def test_template_registry_items_returns_mappings():
    registry = TemplateRegistry()
    template = ScaffoldingTemplate("package.json")
    registry.register("package.json", template)

    items = registry.items()
    assert items == [(Path("package.json"), template)]
