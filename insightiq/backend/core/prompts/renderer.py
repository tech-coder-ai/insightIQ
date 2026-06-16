from __future__ import annotations

from jinja2 import Template, TemplateError


def render_template(body: str, variables: dict[str, object]) -> str:
    try:
        return Template(body).render(**variables)
    except TemplateError as e:
        raise ValueError(f"template render error: {e}") from e
