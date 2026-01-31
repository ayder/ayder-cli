from ayder_cli import client
from ayder_cli import fs_tools
from openai import OpenAI
import os

def test_workflow():
    print("Testing Agentic Workflow (V2)...")
    api_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    MODEL = "qwen3-coder:latest"
    
    prompt = "Read the first 5 lines of client.py and then run 'ls -la' in the shell."
    
    messages = [
        {"role": "system", "content": client.SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    for i in range(3):
        print(f"\n--- Step {i+1} ---")
        response = api_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=fs_tools.tools_schema
        )
        
        msg = response.choices[0].message
        messages.append(msg)
        
        # Handle Standard API calls
        if msg.tool_calls:
            for tc in msg.tool_calls:
                print(f"API Tool: {tc.function.name}({tc.function.arguments})")
                res = fs_tools.execute_tool_call(tc.function.name, tc.function.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "content": str(res)
                })
                print(f"Result: {str(res)[:50]}...")
        
        # Handle Custom Text calls
        else:
            calls = client.parse_custom_tool_calls(msg.content)
            if calls:
                for call in calls:
                    print(f"Text Tool: {call['name']}({call['arguments']})")
                    res = fs_tools.execute_tool_call(call['name'], call['arguments'])
                    messages.append({
                        "role": "user", 
                        "content": f"Tool '{call['name']}' execution result: {res}"
                    })
                    print(f"Result: {str(res)[:50]}...")
            elif msg.content:
                print(f"Assistant: {msg.content}")
                break
            else:
                print("No output or tools.")
                break

if __name__ == "__main__":
    test_workflow()