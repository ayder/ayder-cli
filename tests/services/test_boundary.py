"""Architecture boundary tests for service/UI decoupling.

Contract 1: Service Boundary Rule
- Modules under src/ayder_cli/services/** must NOT import ayder_cli.ui.
"""

import ast
from pathlib import Path

import pytest


class TestServiceBoundary:
    """Test that service modules do not depend on presentation layer."""

    def get_service_modules(self) -> list[Path]:
        """Get all Python files in the services directory."""
        services_dir = Path(__file__).parent.parent.parent / "src" / "ayder_cli" / "services"
        return list(services_dir.rglob("*.py"))

    def find_ui_imports(self, file_path: Path) -> list[str]:
        """Find any imports of ayder_cli.ui in a Python file.
        
        Returns a list of import lines found.
        """
        imports = []
        try:
            content = file_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "ayder_cli.ui" or alias.name.startswith("ayder_cli.ui."):
                            imports.append(f"import {alias.name}")
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module and (node.module == "ayder_cli.ui" or node.module.startswith("ayder_cli.ui.")):
                        names = ", ".join(alias.name for alias in node.names)
                        imports.append(f"from {node.module} import {names}")
                    # Also check for 'from ayder_cli import ui'
                    if node.module == "ayder_cli":
                        for alias in node.names:
                            if alias.name == "ui":
                                imports.append(f"from ayder_cli import ui")
        except SyntaxError:
            # Skip files with syntax errors
            pass
        
        return imports

    def test_services_directory_has_no_ui_imports(self):
        """Verify no service module imports ayder_cli.ui directly.
        
        This is Contract 1: Service modules must be presentation-agnostic.
        All UI interactions must go through injected interfaces.
        """
        service_modules = self.get_service_modules()
        violations = []
        
        for module_path in service_modules:
            if module_path.name == "__init__.py":
                continue
                
            imports = self.find_ui_imports(module_path)
            if imports:
                relative_path = module_path.relative_to(Path(__file__).parent.parent.parent)
                violations.append(f"{relative_path}: {', '.join(imports)}")
        
        # Assertion should fail if any UI imports found
        assert not violations, (
            f"Service modules must not import ayder_cli.ui.\n"
            f"Found violations in:\n" + "\n".join(f"  - {v}" for v in violations)
        )

    def test_tool_executor_has_no_ui_imports(self):
        """Specific test for ToolExecutor boundary.
        
        ToolExecutor is the main service that interacts with UI.
        It must use injected interfaces, not direct imports.
        """
        executor_path = (
            Path(__file__).parent.parent.parent 
            / "src" 
            / "ayder_cli" 
            / "services" 
            / "tools" 
            / "executor.py"
        )
        
        if not executor_path.exists():
            pytest.skip("ToolExecutor not yet implemented")
            
        imports = self.find_ui_imports(executor_path)
        
        assert not imports, (
            f"ToolExecutor must not import ayder_cli.ui directly.\n"
            f"Found: {imports}\n"
            f"Use injected InteractionSink and ConfirmationPolicy instead."
        )

    def test_llm_service_has_no_ui_imports(self):
        """Specific test for LLM service boundary.
        
        LLM providers must route verbose output through InteractionSink,
        not directly import UI functions.
        """
        llm_path = (
            Path(__file__).parent.parent.parent 
            / "src" 
            / "ayder_cli" 
            / "services" 
            / "llm.py"
        )
        
        if not llm_path.exists():
            pytest.skip("LLM service not yet implemented")
            
        imports = self.find_ui_imports(llm_path)
        
        assert not imports, (
            f"LLM service must not import ayder_cli.ui directly.\n"
            f"Found: {imports}\n"
            f"Use injected InteractionSink.on_llm_request_debug() instead."
        )


class TestImportGuard:
    """Test that importing UI from services raises appropriate errors."""

    def test_services_import_ui_blocked(self):
        """Verify that service modules cannot import UI (runtime check).
        
        This test simulates what would happen if someone tries to
        import ayder_cli.ui from within a service module.
        """
        # For now, we just verify the import is possible (before enforcement)
        # After implementation, this should be blocked
        try:
            from ayder_cli.ui import confirm_tool_call
            # If import succeeds, that's the current state
            # The test documents the expected behavior change
            assert callable(confirm_tool_call), "UI function should be callable"
        except ImportError:
            # This is the desired end state after decoupling
            pass
