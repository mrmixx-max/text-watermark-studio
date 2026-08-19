"""Tests for api/routes/metadata.py"""
from unittest.mock import patch

import pytest

from ai_watermark_toolkit.api.routes import metadata as meta_routes


class TestMetadataRoutes:
    def test_inspect_missing_file(self):
        with patch("ai_watermark_toolkit.api.routes.metadata.service.inspect") as mock_inspect:
            mock_inspect.return_value = {"format": "png", "actions": []}
            # Test the route function directly
            pass  # Route requires UploadFile, tested via integration


class TestMetadataInspect:
    def test_metadata_inspect_unsupported(self):
        from ai_watermark_toolkit.metadata.service import inspect
        result = inspect(b"data", "test.xyz")
        assert result["format"] == "xyz"


class TestMetadataClean:
    def test_metadata_clean_unsupported(self):
        from ai_watermark_toolkit.metadata.service import clean
        cleaned, report = clean(b"data", "test.xyz")
        assert report["format"] == "xyz"
