from openai import OpenAI

client = OpenAI(
  api_key="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"
)

completion = client.chat.completions.create(
  model="gpt-4o-mini",
  store=True,
  messages=[
    {"role": "user", "content": "write a haiku about ai"}
  ]
)

print(completion.choices[0].message);