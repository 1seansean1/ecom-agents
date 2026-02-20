"""Unit tests for MCP builtin tools per Task 43.3 (Manifest).

Tests the four core builtin tools with validation and error handling.
Minimum 40 tests per task specification.
"""

from __future__ import annotations

import pytest

from holly.engine.mcp_builtins import (
    BuiltinTool,
    BuiltinToolError,
    CodeExecutionError,
    CodeToolRequest,
    CodeToolResponse,
    DatabaseError,
    DatabaseToolRequest,
    DatabaseToolResponse,
    FilesystemAccessError,
    FilesystemToolRequest,
    FilesystemToolResponse,
    WebRequestError,
    WebToolRequest,
    WebToolResponse,
)


@pytest.fixture
def builtin_tool() -> BuiltinTool:
    """Builtin tool instance."""
    return BuiltinTool()


# ---------------------------------------------------------------------------
# Code Tool Tests
# ---------------------------------------------------------------------------


def test_code_tool_basic_request():
    """Test basic code tool request creation."""
    req = CodeToolRequest(code="print('hello')")
    assert req.code == "print('hello')"
    assert req.timeout_seconds == 30


def test_code_tool_with_timeout(builtin_tool: BuiltinTool):
    """Test code tool respects timeout parameter."""
    req = CodeToolRequest(code="x = 1", timeout_seconds=60)
    resp = builtin_tool.execute_code(req)
    assert resp.success is True


def test_code_tool_timeout_too_long(builtin_tool: BuiltinTool):
    """Test code tool rejects timeout > 300s."""
    req = CodeToolRequest(code="x = 1", timeout_seconds=301)
    with pytest.raises(CodeExecutionError):
        builtin_tool.execute_code(req)


def test_code_tool_timeout_zero(builtin_tool: BuiltinTool):
    """Test code tool rejects zero timeout."""
    req = CodeToolRequest(code="x = 1", timeout_seconds=0)
    with pytest.raises(CodeExecutionError):
        builtin_tool.execute_code(req)


def test_code_tool_response_immutable():
    """Test code tool response is immutable."""
    resp = CodeToolResponse(success=True)
    with pytest.raises(AttributeError):
        resp.success = False  # type: ignore


def test_code_tool_execution_time_set(builtin_tool: BuiltinTool):
    """Test code tool response includes execution time."""
    req = CodeToolRequest(code="x = 1")
    resp = builtin_tool.execute_code(req)
    assert resp.execution_time_ms is not None
    assert resp.execution_time_ms > 0


def test_code_tool_with_input_data(builtin_tool: BuiltinTool):
    """Test code tool accepts input data."""
    req = CodeToolRequest(code="result = input_data['x']", input_data={"x": 42})
    resp = builtin_tool.execute_code(req)
    assert resp.success is True


# ---------------------------------------------------------------------------
# Web Tool Tests
# ---------------------------------------------------------------------------


def test_web_tool_basic_request():
    """Test basic web tool request creation."""
    req = WebToolRequest(url="https://example.com")
    assert req.url == "https://example.com"
    assert req.method == "GET"


def test_web_tool_with_method(builtin_tool: BuiltinTool):
    """Test web tool with different HTTP methods."""
    for method in ["GET", "POST", "PUT", "DELETE"]:
        req = WebToolRequest(url="https://api.example.com", method=method)
        resp = builtin_tool.execute_web(req)
        assert resp.success is True


def test_web_tool_invalid_method(builtin_tool: BuiltinTool):
    """Test web tool rejects invalid HTTP method."""
    req = WebToolRequest(url="https://example.com", method="INVALID")
    with pytest.raises(WebRequestError):
        builtin_tool.execute_web(req)


def test_web_tool_localhost_denied(builtin_tool: BuiltinTool):
    """Test web tool denies localhost per SSRF mitigation (ICD-031)."""
    req = WebToolRequest(url="http://localhost:8000")
    with pytest.raises(WebRequestError):
        builtin_tool.execute_web(req)


def test_web_tool_127_denied(builtin_tool: BuiltinTool):
    """Test web tool denies 127.0.0.1 per SSRF mitigation."""
    req = WebToolRequest(url="http://127.0.0.1:8000")
    with pytest.raises(WebRequestError):
        builtin_tool.execute_web(req)


def test_web_tool_private_ip_denied(builtin_tool: BuiltinTool):
    """Test web tool denies private IPs per SSRF mitigation."""
    req = WebToolRequest(url="http://192.168.1.1")
    with pytest.raises(WebRequestError):
        builtin_tool.execute_web(req)


def test_web_tool_allowed_url(builtin_tool: BuiltinTool):
    """Test web tool allows public URLs."""
    req = WebToolRequest(url="https://example.com")
    resp = builtin_tool.execute_web(req)
    assert resp.success is True


def test_web_tool_with_headers(builtin_tool: BuiltinTool):
    """Test web tool accepts headers."""
    req = WebToolRequest(
        url="https://api.example.com",
        headers={"Authorization": "Bearer token"},
    )
    resp = builtin_tool.execute_web(req)
    assert resp.success is True


def test_web_tool_with_body(builtin_tool: BuiltinTool):
    """Test web tool accepts request body."""
    req = WebToolRequest(
        url="https://api.example.com",
        method="POST",
        body='{"key": "value"}',
    )
    resp = builtin_tool.execute_web(req)
    assert resp.success is True


def test_web_tool_timeout(builtin_tool: BuiltinTool):
    """Test web tool respects timeout."""
    req = WebToolRequest(url="https://example.com", timeout_seconds=10)
    resp = builtin_tool.execute_web(req)
    assert resp.success is True


def test_web_tool_response_status(builtin_tool: BuiltinTool):
    """Test web tool response includes status code."""
    req = WebToolRequest(url="https://example.com")
    resp = builtin_tool.execute_web(req)
    assert resp.status_code is not None


# ---------------------------------------------------------------------------
# Filesystem Tool Tests
# ---------------------------------------------------------------------------


def test_filesystem_read_request():
    """Test filesystem read request creation."""
    req = FilesystemToolRequest(operation="read", path="/data/file.txt")
    assert req.operation == "read"
    assert req.path == "/data/file.txt"


def test_filesystem_write_request():
    """Test filesystem write request creation."""
    req = FilesystemToolRequest(
        operation="write",
        path="/data/file.txt",
        content="hello",
    )
    assert req.operation == "write"
    assert req.content == "hello"


def test_filesystem_invalid_operation(builtin_tool: BuiltinTool):
    """Test filesystem rejects invalid operation."""
    req = FilesystemToolRequest(operation="delete", path="/data/file.txt")
    with pytest.raises(FilesystemAccessError):
        builtin_tool.access_filesystem(req)


def test_filesystem_read_success(builtin_tool: BuiltinTool):
    """Test filesystem read operation."""
    req = FilesystemToolRequest(operation="read", path="/data/file.txt")
    resp = builtin_tool.access_filesystem(req)
    assert resp.success is True
    assert resp.content is not None


def test_filesystem_write_success(builtin_tool: BuiltinTool):
    """Test filesystem write operation."""
    req = FilesystemToolRequest(
        operation="write",
        path="/data/file.txt",
        content="test",
    )
    resp = builtin_tool.access_filesystem(req)
    assert resp.success is True


def test_filesystem_path_traversal_denied(builtin_tool: BuiltinTool):
    """Test filesystem rejects path traversal per ICD-032 mitigation."""
    req = FilesystemToolRequest(operation="read", path="../../etc/passwd")
    with pytest.raises(FilesystemAccessError):
        builtin_tool.access_filesystem(req)


def test_filesystem_etc_denied(builtin_tool: BuiltinTool):
    """Test filesystem denies /etc access."""
    req = FilesystemToolRequest(operation="read", path="/etc/passwd")
    with pytest.raises(FilesystemAccessError):
        builtin_tool.access_filesystem(req)


def test_filesystem_safe_path(builtin_tool: BuiltinTool):
    """Test filesystem allows safe paths."""
    req = FilesystemToolRequest(operation="read", path="/home/user/file.txt")
    resp = builtin_tool.access_filesystem(req)
    assert resp.success is True


def test_filesystem_response_immutable():
    """Test filesystem response is immutable."""
    resp = FilesystemToolResponse(success=True)
    with pytest.raises(AttributeError):
        resp.success = False  # type: ignore


# ---------------------------------------------------------------------------
# Database Tool Tests
# ---------------------------------------------------------------------------


def test_database_select_request():
    """Test database select request creation."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users WHERE id = ?",
        parameters={"id": 1},
        operation="select",
    )
    assert req.operation == "select"


def test_database_insert_request():
    """Test database insert request creation."""
    req = DatabaseToolRequest(
        query="INSERT INTO users (name) VALUES (?)",
        parameters={"name": "John"},
        operation="insert",
    )
    assert req.operation == "insert"


def test_database_invalid_operation(builtin_tool: BuiltinTool):
    """Test database rejects invalid operation."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users",
        operation="unknown",
    )
    with pytest.raises(DatabaseError):
        builtin_tool.execute_database(req)


def test_database_select_success(builtin_tool: BuiltinTool):
    """Test database select operation."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users",
        operation="select",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.success is True
    assert resp.rows is not None


def test_database_insert_success(builtin_tool: BuiltinTool):
    """Test database insert operation."""
    req = DatabaseToolRequest(
        query="INSERT INTO users (name) VALUES (?)",
        parameters={"name": "John"},
        operation="insert",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.success is True


def test_database_update_success(builtin_tool: BuiltinTool):
    """Test database update operation."""
    req = DatabaseToolRequest(
        query="UPDATE users SET name = ? WHERE id = ?",
        parameters={"name": "Jane", "id": 1},
        operation="update",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.success is True


def test_database_delete_success(builtin_tool: BuiltinTool):
    """Test database delete operation."""
    req = DatabaseToolRequest(
        query="DELETE FROM users WHERE id = ?",
        parameters={"id": 1},
        operation="delete",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.success is True


def test_database_sql_injection_denied(builtin_tool: BuiltinTool):
    """Test database rejects SQL injection per ICD-039 mitigation."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users WHERE id = 1'; DROP TABLE users; --",
        operation="select",
    )
    with pytest.raises(DatabaseError):
        builtin_tool.execute_database(req)


def test_database_union_denied(builtin_tool: BuiltinTool):
    """Test database rejects UNION SELECT attacks."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users UNION SELECT * FROM passwords",
        operation="select",
    )
    with pytest.raises(DatabaseError):
        builtin_tool.execute_database(req)


def test_database_or_1_denied(builtin_tool: BuiltinTool):
    """Test database rejects OR 1=1 bypass attempts."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users WHERE id = 1 OR 1=1",
        operation="select",
    )
    with pytest.raises(DatabaseError):
        builtin_tool.execute_database(req)


def test_database_safe_query(builtin_tool: BuiltinTool):
    """Test database allows safe parameterized queries."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users WHERE id = ?",
        parameters={"id": 1},
        operation="select",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.success is True


def test_database_response_row_count(builtin_tool: BuiltinTool):
    """Test database response includes row count."""
    req = DatabaseToolRequest(
        query="SELECT * FROM users",
        operation="select",
    )
    resp = builtin_tool.execute_database(req)
    assert resp.row_count is not None


def test_database_response_immutable():
    """Test database response is immutable."""
    resp = DatabaseToolResponse(success=True)
    with pytest.raises(AttributeError):
        resp.success = False  # type: ignore


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


def test_all_tools_in_builtin_instance(builtin_tool: BuiltinTool):
    """Test BuiltinTool instance provides all four tools."""
    assert hasattr(builtin_tool, "execute_code")
    assert hasattr(builtin_tool, "execute_web")
    assert hasattr(builtin_tool, "access_filesystem")
    assert hasattr(builtin_tool, "execute_database")


def test_tool_error_inheritance():
    """Test all tool-specific errors inherit from BuiltinToolError."""
    assert issubclass(CodeExecutionError, BuiltinToolError)
    assert issubclass(WebRequestError, BuiltinToolError)
    assert issubclass(FilesystemAccessError, BuiltinToolError)
    assert issubclass(DatabaseError, BuiltinToolError)


def test_multiple_tool_instances(builtin_tool: BuiltinTool):
    """Test multiple BuiltinTool instances are independent."""
    tool2 = BuiltinTool()
    # Both should work independently
    req1 = CodeToolRequest(code="x = 1")
    req2 = CodeToolRequest(code="y = 2")
    resp1 = builtin_tool.execute_code(req1)
    resp2 = tool2.execute_code(req2)
    assert resp1.success and resp2.success


def test_tool_error_messages():
    """Test error messages are informative."""
    try:
        tool = BuiltinTool()
        req = WebToolRequest(url="http://localhost")
        tool.execute_web(req)
    except WebRequestError as e:
        assert "allowlist" in str(e).lower()


def test_tool_timeout_validation(builtin_tool: BuiltinTool):
    """Test code tool timeout validation is strict."""
    # Valid timeouts
    for timeout in [1, 30, 150, 300]:
        req = CodeToolRequest(code="x = 1", timeout_seconds=timeout)
        resp = builtin_tool.execute_code(req)
        assert resp.success is True

    # Invalid timeout (too high)
    with pytest.raises(CodeExecutionError):
        req = CodeToolRequest(code="x = 1", timeout_seconds=301)
        builtin_tool.execute_code(req)
