import importlib
import pytest

MODS = ["certpath_roadmap_studio.ui_server", ]


@pytest.mark.parametrize("mod", MODS)
@pytest.mark.parametrize("raw,expected", [
    ("/", ""), ("/index.html", "index.html"), ("/assets/app.js", "assets/app.js"),
    ("/../../etc/passwd", ""), ("/static/../../../etc/passwd", ""),
    ("/%2e%2e/%2e%2e/etc/passwd", ""), ("/..%2f..%2fetc/passwd", ""),
    ("/a\\..\\..\\x", ""), ("/C:/Windows/win.ini", ""),
])
def test_safe_rel(mod, raw, expected):
    assert importlib.import_module(mod)._safe_rel(raw) == expected
