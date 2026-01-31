import re


def parse_custom_tool_calls(content):
    """
    Parses custom XML-like tool calls from the model output.
    """
    if not content:
        return []

    calls = []
    # Regex to capture the function block
    func_pattern = re.compile(r"<function=(.*?)>(.*?)</function>", re.DOTALL)
    # Regex to capture parameters inside the block
    param_pattern = re.compile(r"<parameter=(.*?)>(.*?)</parameter>", re.DOTALL)

    for func_match in func_pattern.finditer(content):
        func_name = func_match.group(1).strip()
        body = func_match.group(2)

        args = {}
        for param_match in param_pattern.finditer(body):
            key = param_match.group(1).strip()
            value = param_match.group(2).strip()
            args[key] = value

        calls.append({
            "name": func_name,
            "arguments": args
        })

    return calls
