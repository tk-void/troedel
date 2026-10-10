"""Templates, script and stylesheet have to agree on names. Nothing renders
these pages in a browser during the tests, so this is the net for a class
that was renamed in one file and not in the others."""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "troedel" / "web"
CSS = (WEB / "static" / "troedel.css").read_text(encoding="utf-8")
JS = (WEB / "static" / "troedel.js").read_text(encoding="utf-8")
TEMPLATES = {p.name: p.read_text(encoding="utf-8") for p in (WEB / "templates").glob("*.html")}

STYLED = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"url\([^)]*\)", "", CSS)))
STATE_ONLY = {"sr"}


def classes_in_templates() -> set[str]:
    found: set[str] = set()
    for source in TEMPLATES.values():
        for value in re.findall(r'class="([^"]*)"', source):
            # Jinja expressions inside a class attribute: keep the literal words.
            value = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", value)
            found.update(w for w in value.split() if re.fullmatch(r"[a-zA-Z][\w-]*", w))
        for expression in re.findall(r'class="[^"]*\{\{(.*?)\}\}', source):
            found.update(
                w
                for quoted in re.findall(r"'([^']*)'", expression)
                for w in quoted.split()
                if re.fullmatch(r"[a-z][\w-]*", w)
            )
    return found


def classes_in_script() -> set[str]:
    found: set[str] = set()
    for call in re.findall(r"classList\.(?:add|remove|toggle|contains)\('([\w-]+)'", JS):
        found.add(call)
    for value in re.findall(r"className = '([^']+)'", JS):
        found.update(value.split())
    for value in re.findall(r'class="([^"]+)"', JS):
        found.update(value.split())
    return found


def test_every_class_in_a_template_is_styled() -> None:
    missing = classes_in_templates() - STYLED - STATE_ONLY
    # Hooks without a style of their own.
    missing -= {"draft", "code", "logo", "lead", "manager", "steps"}
    assert not missing, f"used in templates, not in the stylesheet: {sorted(missing)}"


def test_every_class_the_script_sets_is_styled() -> None:
    missing = classes_in_script() - STYLED
    assert not missing, f"set by the script, not in the stylesheet: {sorted(missing)}"


def test_the_script_only_looks_for_things_that_exist() -> None:
    """Every id and data attribute the script selects appears in a template
    or is created by the script itself."""
    everything = "\n".join(TEMPLATES.values()) + JS
    for ident in set(re.findall(r"\$\('#([\w-]+)'", JS)):
        if ident.endswith("-"):  # a prefix that is completed at run time
            continue
        assert f'id="{ident}"' in everything or f"id = '{ident}'" in JS, f"#{ident}"
    for attribute in set(re.findall(r"\[data-([\w-]+)", JS)):
        assert f"data-{attribute}" in "\n".join(TEMPLATES.values()) or f"data-{attribute}" in JS.replace(
            f"[data-{attribute}", ""
        ), f"data-{attribute}"


def test_no_inline_handlers_or_unnonced_scripts_in_templates() -> None:
    """The content security policy would block them silently."""
    for name, source in TEMPLATES.items():
        assert not re.search(r"\son[a-z]+\s*=", source), name
        for tag in re.findall(r"<script[^>]*>", source):
            assert "src=" in tag or 'nonce="{{ nonce }}"' in tag, f"{name}: {tag}"


def test_icons_used_exist() -> None:
    defined = set(re.findall(r"name == '([\w-]+)'", TEMPLATES["_icons.html"]))
    for name, source in TEMPLATES.items():
        for icon in re.findall(r"icon\('([\w-]+)'\)", source):
            assert icon in defined, f"{name}: icon {icon!r}"


def test_api_paths_in_the_script_are_routes() -> None:
    import tempfile

    from troedel.config import Settings
    from troedel.web.app import create_app

    with tempfile.TemporaryDirectory() as folder:
        app = create_app(Settings(data_dir=Path(folder)), start=False)
        routes = {re.sub(r"\{[^}]+\}", "*", r.path) for r in app.routes}
    used = set(re.findall(r"'(/(?:api|settings)/[\w/-]*)'", JS))
    for path in used:
        candidates = {path.rstrip("/"), path + "*", path.rstrip("/") + "/*"}
        assert candidates & routes or any(r.startswith(path) for r in routes), path
