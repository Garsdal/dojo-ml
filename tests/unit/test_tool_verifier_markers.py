"""_parse_tool_markers correctly extracts per-tool results and errors."""

from dojo.runtime.tool_verifier import _parse_tool_markers


def test_parse_result_marker():
    stdout = '__DOJO_TOOL_RESULT__:{"tool": "load_data", "sample": {"y_test": {"len": 100}}}\n'
    results, errors = _parse_tool_markers(stdout)
    assert "load_data" in results
    assert errors == {}


def test_parse_error_marker():
    stdout = '__DOJO_TOOL_ERROR__:{"tool": "evaluate", "type": "ValueError", "message": "bad", "traceback": ""}\n'
    results, errors = _parse_tool_markers(stdout)
    assert results == {}
    assert "evaluate" in errors
    assert errors["evaluate"]["message"] == "bad"


def test_parse_both_markers():
    stdout = (
        '__DOJO_TOOL_RESULT__:{"tool": "load_data", "sample": {}}\n'
        '__DOJO_TOOL_ERROR__:{"tool": "evaluate", "type": "KeyError", "message": "x", "traceback": ""}\n'
    )
    results, errors = _parse_tool_markers(stdout)
    assert "load_data" in results
    assert "evaluate" in errors


def test_parse_ignores_noise():
    stdout = (
        "INFO: loading dataset\n"
        "__DOJO_TOOL_RESULT__:bad json\n"
        '__DOJO_TOOL_RESULT__:{"tool": "load_data", "sample": {}}\n'
    )
    results, _errors = _parse_tool_markers(stdout)
    assert "load_data" in results
