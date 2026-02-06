import re
from typing import List, Dict, Any


def _build_single_param_map() -> Dict[str, str]:
    """Build a map of single-param tools by analyzing tool schemas.
    
    Returns a dict mapping tool name to its single required parameter name.
    Only includes tools with exactly one required parameter.
    """
    from ayder_cli.tools.schemas import tools_schema
    
    single_param_map = {}
    for tool in tools_schema:
        func = tool.get("function", {})
        name = func.get("name")
        params = func.get("parameters", {})
        required = params.get("required", [])
        
        if name and len(required) == 1:
            single_param_map[name] = required[0]
    
    return single_param_map


# Auto-generated map of single-param tools from schemas
_SINGLE_PARAM_TOOLS = _build_single_param_map()


def parse_custom_tool_calls(content: str) -> List[Dict[str, Any]]:
    """
    Enhanced parser handling:
    - Standard: <function=name><parameter=key>value</parameter></function>
    - Lazy: <function=name>value</function> (single-param tools only)
    - Errors: Returns {"error": "message"} for malformed input
    """
    if not content:
        return []

    calls = []
    func_pattern = re.compile(r"<function=(.*?)>(.*?)</function>", re.DOTALL)
    param_pattern = re.compile(r"<parameter=(.*?)>(.*?)</parameter>", re.DOTALL)

    for func_match in func_pattern.finditer(content):
        func_name = func_match.group(1).strip()
        body = func_match.group(2).strip()

        if not func_name:
            calls.append({
                "name": "unknown",
                "arguments": {},
                "error": "Malformed tool call: function name is empty"
            })
            continue

        param_matches = list(param_pattern.finditer(body))

        if param_matches:
            # Standard format with parameters
            args = {}
            for pm in param_matches:
                key = pm.group(1).strip()
                value = pm.group(2).strip()
                if key:
                    args[key] = value
            calls.append({"name": func_name, "arguments": args})

        elif body and "<parameter" not in body:
            # Lazy format - try to infer parameter
            inferred = _infer_parameter_name(func_name)
            if inferred:
                calls.append({"name": func_name, "arguments": {inferred: body}})
            else:
                calls.append({
                    "name": func_name,
                    "arguments": {},
                    "error": f"Missing <parameter> tags. Use: <function={func_name}><parameter=name>value</parameter></function>"
                })
        else:
            calls.append({
                "name": func_name,
                "arguments": {},
                "error": "Tool call has no parameters"
            })

    return calls


def _infer_parameter_name(func_name: str) -> str:
    """Infer parameter for single-param tools only.
    
    The single-param tool map is auto-generated from tool schemas by
    finding tools with exactly one required parameter.
    """
    return _SINGLE_PARAM_TOOLS.get(func_name, "")
