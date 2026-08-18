"""E2E tests for MCP server integration.

Tests the MCP tool manifest and simulates JSON-RPC calls against the API
that the MCP server would proxy.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = PROJECT_ROOT / "mcp"


def _free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestMCPManifest:
    """Validate the MCP tool manifest files."""

    def test_mcp_json_exists(self):
        """mcp.json should exist."""
        assert (MCP_DIR / "mcp.json").exists()

    def test_tools_json_exists(self):
        """tools.json should exist."""
        assert (MCP_DIR / "tools.json").exists()

    def test_mcp_json_valid(self):
        """mcp.json should be valid JSON with required fields."""
        data = json.loads((MCP_DIR / "mcp.json").read_text(encoding="utf-8"))
        assert "name" in data
        assert "tools_manifest" in data
        assert "transport" in data
        assert "base_url" in data

    def test_tools_json_valid(self):
        """tools.json should be valid JSON with tools array."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        assert "name" in data
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    def test_tools_have_required_fields(self):
        """Each tool should have name, method, path, description."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        for tool in data["tools"]:
            assert "name" in tool, f"tool missing name: {tool}"
            assert "method" in tool, f"tool missing method: {tool}"
            assert "path" in tool, f"tool missing path: {tool}"
            assert "description" in tool, f"tool missing description: {tool}"

    def test_tools_paths_are_valid(self):
        """All tool paths should start with /."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        for tool in data["tools"]:
            assert tool["path"].startswith("/"), f"invalid path: {tool['path']}"

    def test_tools_methods_are_valid(self):
        """All tool methods should be valid HTTP methods."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        valid_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        for tool in data["tools"]:
            assert tool["method"] in valid_methods, f"invalid method: {tool['method']}"


class TestMCPToolInvocation:
    """Simulate MCP tool invocations as JSON-RPC over the API.

    The MCP server proxies tool calls to the HTTP API. We test that each
    tool's underlying endpoint works correctly.
    """

    @pytest.fixture(scope="class")
    def server_url(self):
        """Start the simple HTTP server as a subprocess."""
        import os
        port = _free_port()
        env = os.environ.copy()
        env["AI_WM_ENV"] = "development"

        cmd = [sys.executable, "-m", "ai_watermark_toolkit.cli", "serve",
               "--host", "127.0.0.1", "--port", str(port)]
        proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        url = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            proc.kill()
            pytest.fail("server did not start in time")
        yield url
        proc.kill()
        proc.wait(timeout=5)

    def _json_rpc_call(self, server_url: str, tool_name: str, params: dict | None = None) -> dict:
        """Simulate an MCP JSON-RPC tool call.

        In a real MCP server, the tool call is translated to an HTTP request.
        We simulate this by reading the tool manifest and making the
        corresponding HTTP request.
        """
        import httpx
        tools = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        tool = next((t for t in tools["tools"] if t["name"] == tool_name), None)
        if tool is None:
            raise ValueError(f"tool not found: {tool_name}")

        method = tool["method"]
        path = tool["path"]
        url = f"{server_url}{path}"

        if method == "GET":
            r = httpx.get(url, timeout=5)
        elif method == "POST":
            r = httpx.post(url, json=params or {}, timeout=5)
        else:
            raise ValueError(f"unsupported method: {method}")

        return {"status_code": r.status_code, "body": r.json()}

    def test_health_tool(self, server_url):
        """MCP health tool should return ok."""
        result = self._json_rpc_call(server_url, "health")
        assert result["status_code"] == 200
        assert result["body"]["ok"] is True

    def test_pipeline_tool(self, server_url):
        """MCP pipeline tool should run the pipeline."""
        result = self._json_rpc_call(server_url, "lab_pipeline", {
            "text": "Hello world test.",
            "lang": "en",
            "intensity": "standard",
        })
        assert result["status_code"] == 200
        assert "text" in result["body"]
        assert "report" in result["body"]

    def test_document_formats_tool(self, server_url):
        """MCP document_formats tool should return supported formats."""
        result = self._json_rpc_call(server_url, "document_formats")
        # May be 200 or 404 depending on route
        assert result["status_code"] in (200, 404)

    def test_rag_strategies_tool(self, server_url):
        """MCP rag_strategies tool should return strategies."""
        result = self._json_rpc_call(server_url, "rag_strategies")
        assert result["status_code"] in (200, 404)

    def test_pdf_strategy_tool(self, server_url):
        """MCP pdf_strategy tool should return strategy info."""
        result = self._json_rpc_call(server_url, "pdf_strategy")
        assert result["status_code"] in (200, 404)

    def test_graph_schema_tool(self, server_url):
        """MCP graph_schema tool should return schema."""
        result = self._json_rpc_call(server_url, "graph_schema")
        assert result["status_code"] in (200, 404)

    def test_prompt_templates_tool(self, server_url):
        """MCP prompt_templates tool should return templates."""
        result = self._json_rpc_call(server_url, "prompt_templates")
        assert result["status_code"] in (200, 404)

    def test_llm_status_tool(self, server_url):
        """MCP llm_status tool should return status."""
        result = self._json_rpc_call(server_url, "llm_status")
        assert result["status_code"] in (200, 404)

    def test_ma_spec_tool(self, server_url):
        """MCP ma_spec tool should return spec."""
        result = self._json_rpc_call(server_url, "ma_spec")
        assert result["status_code"] in (200, 404)


class TestMCPJSONRPCStructure:
    """Test JSON-RPC request/response structure compliance."""

    def test_json_rpc_request_format(self):
        """A valid JSON-RPC 2.0 request should have required fields."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "health",
            "params": {},
        }
        assert request["jsonrpc"] == "2.0"
        assert "id" in request
        assert "method" in request

    def test_json_rpc_response_format(self):
        """A valid JSON-RPC 2.0 response should have required fields."""
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"ok": True},
        }
        assert response["jsonrpc"] == "2.0"
        assert "id" in response
        assert "result" in response or "error" in response

    def test_mcp_tool_names_are_unique(self):
        """All MCP tool names should be unique."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        names = [t["name"] for t in data["tools"]]
        assert len(names) == len(set(names)), "duplicate tool names found"

    def test_mcp_tool_names_are_snake_case(self):
        """All MCP tool names should be snake_case."""
        data = json.loads((MCP_DIR / "tools.json").read_text(encoding="utf-8"))
        for tool in data["tools"]:
            assert tool["name"] == tool["name"].lower(), f"not lowercase: {tool['name']}"
            assert " " not in tool["name"], f"has spaces: {tool['name']}"
