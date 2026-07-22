from openai import OpenAI
client = OpenAI(
    base_url="http://127.0.0.1:8045/v1",
    api_key="sk-4c2ec6f80d904f35b2c1598b1464aaca"
)
try:
    response = client.chat.completions.create(
        model="gemini-3-flash",
        messages=[{"role": "user", "content": "Hello"}]
    )
    print(response.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
