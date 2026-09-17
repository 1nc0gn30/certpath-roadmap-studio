"""Tests for Model Context Protocol (MCP) server in mcp_server.py."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from certpath_roadmap_studio.mcp_server import MCPServer


@pytest.fixture
def mcp_server(temp_catalog, sample_dag, sample_planner) -> MCPServer:
    """Return an MCPServer instance configured with test dependencies."""
    return MCPServer(
        catalog=temp_catalog,
        dag_engine=sample_dag,
        planner=sample_planner,
    )


def test_mcp_initialize(mcp_server: MCPServer):
    """Verify JSON-RPC initialize handshake."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert "result" in resp
    res = resp["result"]
    assert res["protocolVersion"] == "2024-11-05"
    assert res["serverInfo"]["name"] == "certpath-roadmap-studio"
    assert "tools" in res["capabilities"]


def test_mcp_ping(mcp_server: MCPServer):
    """Verify ping method."""
    req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 2
    assert resp["result"] == {}


def test_mcp_tools_list(mcp_server: MCPServer):
    """Verify listing all registered MCP tools."""
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}

    expected_tools = {
        "certpath_search",
        "certpath_resolve_prereqs",
        "certpath_plan_career",
        "certpath_compare",
        "certpath_export_dag",
        "certpath_roles",
        "certpath_catalog_stats",
        "certpath_diagnostics",
    }
    for expected in expected_tools:
        assert expected in tool_names


def test_mcp_tool_call_search(mcp_server: MCPServer):
    """Verify invoking certpath_search tool."""
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "certpath_search",
            "arguments": {"query": "Networking"},
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    content = resp["result"]["content"]
    assert len(content) > 0
    text = content[0]["text"]
    assert "Networking Basics" in text or "cert-entry-2" in text


def test_mcp_tool_call_prereqs(mcp_server: MCPServer):
    """Verify invoking certpath_resolve_prereqs tool."""
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "certpath_resolve_prereqs",
            "arguments": {"cert_id": "cert-adv-1", "include_target": True},
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "cert-adv-1" in text
    assert "cert-entry-1" in text


def test_mcp_tool_call_plan_career(mcp_server: MCPServer):
    """Verify invoking certpath_plan_career tool."""
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "certpath_plan_career",
            "arguments": {
                "target": "cloud_sec_lead",
                "weekly_hours": 12,
            },
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "Cloud Security Lead" in text or "cert-adv-1" in text


def test_mcp_tool_call_compare(mcp_server: MCPServer):
    """Verify invoking certpath_compare tool."""
    req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "certpath_compare",
            "arguments": {"cert_ids": ["cert-entry-1", "cert-inter-1"]},
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "Foundations of Cloud Computing" in text
    assert "Cloud Solutions Architect" in text


def test_mcp_tool_call_export_dag(mcp_server: MCPServer):
    """Verify invoking certpath_export_dag tool."""
    req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "certpath_export_dag",
            "arguments": {"format": "mermaid", "role": "cloud_sec_lead"},
        },
    }
    resp = mcp_server.handle_request(req)
    assert resp is not None
    assert "result" in resp
    text = resp["result"]["content"][0]["text"]
    assert "flowchart" in text or "graph" in text


def test_mcp_unknown_method_and_unknown_tool(mcp_server: MCPServer):
    """Verify error responses for unknown JSON-RPC method and nonexistent tool."""
    # Unknown method
    req1 = {"jsonrpc": "2.0", "id": 9, "method": "invalid/method"}
    resp1 = mcp_server.handle_request(req1)
    assert resp1 is not None
    assert "error" in resp1
    assert resp1["error"]["code"] == -32601

    # Unknown tool
    req2 = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {"name": "non_existent_tool"},
    }
    resp2 = mcp_server.handle_request(req2)
    assert resp2 is not None
    assert "error" in resp2 or resp2.get("result", {}).get("isError") is True
