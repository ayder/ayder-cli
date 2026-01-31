from ayder_cli import client
from ayder_cli import fs_tools
from openai import OpenAI

# Mock the OpenAI client slightly or just run a single turn loop
# Actually, I'll just use the parsing logic directly to verify it works on the known output format
# and then run a full integration test.

def test_parsing():
    sample_output = """
    I will create the file for you.
    <function=write_file>
    <parameter=file_path>
    test_result_v3.txt
    </parameter>
    <parameter=content>
    Parsing works!
    </parameter>
    </function>
    """
    
    print("Testing Parser...")
    calls = client.parse_custom_tool_calls(sample_output)
    if len(calls) == 1 and calls[0]['name'] == 'write_file':
        print(f"SUCCESS: Parser found {calls[0]}")
    else:
        print(f"FAILURE: Parser returned {calls}")

def test_integration():
    print("\nTesting Integration...")
    # Initialize client locally
    api_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    MODEL = "qwen3-coder:latest"
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Create a file named 'integration_test.txt' with content 'Integration successful'."}
    ]
    
    response = api_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=fs_tools.tools_schema
    )
    
    content = response.choices[0].message.content
    print(f"Model Output: {content}")
    
    calls = client.parse_custom_tool_calls(content)
    if calls:
        for call in calls:
            print(f"Executing: {call['name']}")
            res = fs_tools.execute_tool_call(call['name'], call['arguments'])
            print(f"Result: {res}")
    else:
        print("No custom calls found in output.")

if __name__ == "__main__":
    test_parsing()
    test_integration()
