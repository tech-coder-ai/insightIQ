from __future__ import annotations

import importlib

from core.export.base import EXPORTERS, IExporter


class ExporterFactory:
    @staticmethod
    def create(format_key: str) -> IExporter:
        for module in (
            "core.export.exporters.markdown",
            "core.export.exporters.pdf",
            "core.export.exporters.pptx",
        ):
            try:
                importlib.import_module(module)
            except ModuleNotFoundError:
                pass
        return EXPORTERS.create(format_key)

    @staticmethod
    def keys() -> list[str]:
        ExporterFactory.create("markdown")
        return EXPORTERS.keys()
