"""Tests for tool result types."""


from ayder_cli.core.result import ToolSuccess, ToolError


class TestToolSuccessBackwardsCompat:
    """Test that ToolSuccess behaves as a str."""

    def test_isinstance_str(self):
        assert isinstance(ToolSuccess("ok"), str)

    def test_string_equality(self):
        assert ToolSuccess("ok") == "ok"

    def test_string_contains(self):
        assert "ok" in ToolSuccess("ok result")

    def test_startswith(self):
        assert ToolSuccess("Successfully wrote").startswith("Successfully")

    def test_fstring(self):
        result = ToolSuccess("done")
        assert f"Result: {result}" == "Result: done"

    def test_str_conversion(self):
        assert str(ToolSuccess("value")) == "value"

    def test_empty_value(self):
        s = ToolSuccess()
        assert s == ""
        assert s.is_success


class TestToolErrorBackwardsCompat:
    """Test that ToolError behaves as a str."""

    def test_isinstance_str(self):
        assert isinstance(ToolError("Error: x"), str)

    def test_string_equality(self):
        assert ToolError("Error: x") == "Error: x"

    def test_startswith(self):
        assert ToolError("Error: something").startswith("Error")

    def test_string_contains(self):
        assert "Error" in ToolError("Error: failed")

    def test_fstring(self):
        result = ToolError("Error: fail")
        assert f"Got: {result}" == "Got: Error: fail"

    def test_str_conversion(self):
        assert str(ToolError("Error: x")) == "Error: x"


class TestToolSuccessProperties:
    """Test ToolSuccess type properties."""

    def test_is_success(self):
        assert ToolSuccess("ok").is_success is True

    def test_is_error(self):
        assert ToolSuccess("ok").is_error is False

    def test_repr(self):
        r = repr(ToolSuccess("ok"))
        assert "ToolSuccess" in r
        assert "ok" in r


class TestToolErrorProperties:
    """Test ToolError type properties."""

    def test_is_success(self):
        assert ToolError("Error: x").is_success is False

    def test_is_error(self):
        assert ToolError("Error: x").is_error is True

    def test_default_category(self):
        assert ToolError("Error: x").category == "general"

    def test_custom_category(self):
        assert ToolError("Error: x", category="security").category == "security"

    def test_repr(self):
        r = repr(ToolError("Error: x", category="security"))
        assert "ToolError" in r
        assert "Error: x" in r
        assert "security" in r


class TestToolErrorCategories:
    """Test all supported error categories."""

    def test_security_category(self):
        e = ToolError("Security Error: path traversal", "security")
        assert e.category == "security"

    def test_validation_category(self):
        e = ToolError("Validation Error: missing param", "validation")
        assert e.category == "validation"

    def test_execution_category(self):
        e = ToolError("Error: Command timed out", "execution")
        assert e.category == "execution"

    def test_general_category(self):
        e = ToolError("Error: not found", "general")
        assert e.category == "general"


class TestIsinstanceDistinction:
    """Test isinstance checks distinguish the two types."""

    def test_success_is_not_error(self):
        result = ToolSuccess("ok")
        assert isinstance(result, ToolSuccess)
        assert not isinstance(result, ToolError)

    def test_error_is_not_success(self):
        result = ToolError("Error: x")
        assert isinstance(result, ToolError)
        assert not isinstance(result, ToolSuccess)

    def test_both_are_str(self):
        assert isinstance(ToolSuccess("ok"), str)
        assert isinstance(ToolError("Error: x"), str)
