from ayder_cli import fs_tools
from openai import OpenAI
import json

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

MODEL = "qwen3-coder:latest"

def test_interaction():
    # Stronger instruction
    prompt = "Call the function write_file to save the text 'It works!' into 'test_result.txt'."
    print(f"User: {prompt}")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant. You MUST use the provided tools to answer questions. Do not just describe the action."},
        {"role": "user", "content": prompt}
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=fs_tools.tools_schema,
        tool_choice="auto" 
    )

    msg = response.choices[0].message
    if msg.tool_calls:
        print("SUCCESS: Tool calls detected.")
        for tc in msg.tool_calls:
            print(f"Function: {tc.function.name}")
            print(f"Args: {tc.function.arguments}")
            # Execute
            fs_tools.execute_tool_call(tc.function.name, tc.function.arguments)
    else:
        print("FAILURE: No tool calls detected.")
        print(f"Content: {msg.content}")

if __name__ == "__main__":
    test_interaction()
