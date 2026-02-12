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


def _normalize_tool_call_markup(content: str) -> str:
    """Normalize model-specific tool call markup variations.

    Some models (e.g. Ministral) wrap calls in <tool_call>...</tool_call> and
    may omit the closing </function> tag.  This normaliser:
    1. Strips outer <tool_call> wrappers.
    2. Adds a missing </function> when the block ends with </tool_call>.
    """
    # Unwrap <tool_call> ... </tool_call> blocks, keeping inner content
    content = re.sub(
        r"<tool_call>\s*(.*?)\s*</tool_call>",
        lambda m: m.group(1) if "</function>" in m.group(1)
        else m.group(1) + "</function>",
        content,
        flags=re.DOTALL,
    )
    return content


def parse_custom_tool_calls(content: str) -> List[Dict[str, Any]]:
    """
    Enhanced parser handling:
    - Standard: <function=name><parameter=key>value</parameter></function>
    - Wrapped:  <tool_call><function=name>...</function></tool_call>
    - Wrapped (no close): <tool_call><function=name>...</tool_call>
    - Lazy: <function=name>value</function> (single-param tools only)
    - Errors: Returns {"error": "message"} for malformed input
    """
    if not content:
        return []

    # Normalise model-specific wrappers before parsing
    content = _normalize_tool_call_markup(content)

    calls = []
    func_pattern = re.compile(r"<function=(.*?)>(.*?)</function>", re.DOTALL)
    param_pattern = re.compile(r"<parameter=(.*?)>(.*?)</parameter>", re.DOTALL)
    # Fallback: <parameter=key>value (no closing </parameter>)
    param_unclosed = re.compile(r"<parameter=(.*?)>(.*)", re.DOTALL)

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

        elif not param_matches and "<parameter=" in body:
            # Unclosed parameters — <parameter=key>value without </parameter>
            unclosed_matches = list(param_unclosed.finditer(body))
            if unclosed_matches:
                args = {}
                for um in unclosed_matches:
                    key = um.group(1).strip()
                    value = um.group(2).strip()
                    if key:
                        args[key] = value
                calls.append({"name": func_name, "arguments": args})
            else:
                calls.append({"name": func_name, "arguments": {}})

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
            # Empty body, no parameters — valid for tools with no required params
            calls.append({"name": func_name, "arguments": {}})

    return calls


def _infer_parameter_name(func_name: str) -> str:
    """Infer parameter for single-param tools only.
    
    The single-param tool map is auto-generated from tool schemas by
    finding tools with exactly one required parameter.
    """
    return _SINGLE_PARAM_TOOLS.get(func_name, "")
