from ayder_cli import fs_tools
from openai import OpenAI
import json
import sys

# Initialize client
client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)

MODEL = "qwen3-coder:latest"

def test_interaction():
    prompt = "Create a file named 'test_result.txt' with the content 'It works!'."
    print(f"User: {prompt}")
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant with file tools."},
        {"role": "user", "content": prompt}
    ]

    # 1. Send request
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=fs_tools.tools_schema,
        tool_choice="auto"
    )

    msg = response.choices[0].message
    tool_calls = msg.tool_calls

    if tool_calls:
        print("Model requested tool calls.")
        for tool_call in tool_calls:
            print(f"Tool: {tool_call.function.name}")
            # Execute
            result = fs_tools.execute_tool_call(
                tool_call.function.name, 
                tool_call.function.arguments
            )
            print(f"Result: {result}")
            
            messages.append(msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": str(result)
            })

        # 2. Get final response
        final = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=fs_tools.tools_schema
        )
        print(f"Assistant: {final.choices[0].message.content}")
    else:
        print("Model did NOT call a tool.")
        print(f"Response: {msg.content}")

if __name__ == "__main__":
    test_interaction()
