"""Casing and inline-math rules for the titles a UI-enabled form shows.

See "Titles" in `docs/gui-definition-spec/gui-definition.md`. The walk visits what the frontend
labels: group names, root elements, the blocks a block_union or block_dictionary offers, and every
field that declares a `ui_element`, with its `title_by_key` option titles. Fields without a
`ui_element` are internals the frontend never labels.
"""

import re
from collections.abc import Iterator

import pytest

from obi_one.core.schema import SchemaKey, UIElement

from .validators.shared import openapi_schema, resolve_ref

VARIANT_ROOTS = {UIElement.BLOCK_UNION, UIElement.BLOCK_DICTIONARY}
PARENTHESES = re.compile(r"\([^)]*\)")
MAX_ACRONYM_LENGTH = 4
OPTION = "<option>"  # key reported for a `title_by_key` option title


def forms() -> list[tuple[str, dict]]:
    found = []
    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue
        ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        form = resolve_ref(openapi_schema, ref)
        if form.get(SchemaKey.UI_ENABLED):
            found.append((ref.split("/")[-1], form))
    return found


def merged(node: dict) -> dict:
    """Resolve a `$ref`, keeping the sibling keys (a field's own title) over the target's."""
    ref = node.get("$ref")
    if ref is None:
        return node
    return {**resolve_ref(openapi_schema, ref), **{k: v for k, v in node.items() if k != "$ref"}}


def variants(node: dict) -> list[dict]:
    if node.get(SchemaKey.UI_ELEMENT) == UIElement.BLOCK_UNION:
        return node.get("oneOf", [])
    additional = node.get("additionalProperties", {})
    return additional.get("oneOf") or [additional]


def children(node: dict, key: str | None, where: str) -> Iterator[tuple]:
    for child_key, child in node.get("properties", {}).items():
        if child_key != "type":
            yield child, child_key, f"{where}.{child_key}"
    for branch in (*node.get("anyOf", []), *node.get("oneOf", [])):
        yield branch, key, where
    if isinstance(node.get("items"), dict):
        yield node["items"], key, where


def labelled(node: dict, key: str | None, where: str, seen: frozenset) -> Iterator[tuple]:
    """Yield `(where, key, title)` for every title the frontend shows under `node`."""
    ref = node.get("$ref")
    if ref in seen:
        return
    seen |= {ref} - {None}
    node = merged(node)
    if node.get(SchemaKey.UI_HIDDEN):
        return

    ui_element = node.get(SchemaKey.UI_ELEMENT)
    if ui_element is not None:
        yield where, key, node.get("title")
        for option, title in node.get(SchemaKey.TITLE_BY_KEY, {}).items():
            yield f"{where}[{option}]", OPTION, title

    if ui_element in VARIANT_ROOTS:
        for variant in variants(node):
            title = merged(variant).get("title")
            yield f"{where}<{title}>", None, title
            yield from labelled(variant, None, f"{where}<{title}>", seen)
        return

    for child, child_key, child_where in children(node, key, where):
        yield from labelled(child, child_key, child_where, seen)


def form_titles(form: dict) -> Iterator[tuple]:
    for key, root in form.get("properties", {}).items():
        if key != "type":
            yield from labelled(root, key, key, frozenset())


def pydantic_default_title(key: str) -> str:
    return key.title().replace("_", " ")


def is_all_caps(title: str) -> bool:
    """Whether a title is written in capitals.

    Parenthesised parts like "(NEURON)" are ignored, and so is a lone acronym like "RMP".
    """
    words = re.findall(r"[A-Za-z]+", PARENTHESES.sub("", title))
    if not words or not all(word.isupper() for word in words):
        return False
    return len(words) > 1 or len(words[0]) > MAX_ACRONYM_LENGTH


FORMS = forms()
FORM_IDS = [name for name, _ in FORMS]


@pytest.mark.parametrize(("name", "form"), FORMS, ids=FORM_IDS)
def test_titles_are_not_all_caps(name, form):
    # Option titles often name a tool ("NEURON"), so only fields, blocks and groups are checked.
    shouting = [
        (where, title)
        for where, key, title in form_titles(form)
        if key != OPTION and title and is_all_caps(title)
    ]
    shouting += [
        ("group", group) for group in form.get(SchemaKey.GROUP_ORDER, []) if is_all_caps(group)
    ]
    assert not shouting, f"{name}: write titles in sentence case, not all caps: {shouting}"


@pytest.mark.parametrize(("name", "form"), FORMS, ids=FORM_IDS)
def test_titles_are_written_by_hand(name, form):
    defaults = [
        (where, title)
        for where, key, title in form_titles(form)
        if key and "_" in key and title == pydantic_default_title(key)
    ]
    assert not defaults, (
        f"{name}: give these fields an explicit sentence-case title= instead of pydantic's"
        f" default: {defaults}"
    )


@pytest.mark.parametrize(("name", "form"), FORMS, ids=FORM_IDS)
def test_title_math_is_closed(name, form):
    unclosed = [
        (where, title) for where, _, title in form_titles(form) if title and title.count("$") % 2
    ]
    in_groups = [group for group in form.get(SchemaKey.GROUP_ORDER, []) if "$" in group]
    assert not unclosed, f"{name}: inline math needs a closing $: {unclosed}"
    assert not in_groups, f"{name}: group names are shown uppercase, so no math: {in_groups}"
