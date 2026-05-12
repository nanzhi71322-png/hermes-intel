from config.clients import llm_client, redis_client
from config.settings import DEEPSEEK_MODEL


SYSTEM_PROMPT = """
you are hermes-core

rules:
- concise
- technical
- no fluff
- no emojis
- prioritize execution
- give direct answers
"""


async def ask_llm(user_id, text):
    history_key = f"memory:{user_id}"

    history = redis_client.lrange(history_key, 0, 10)

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for item in reversed(history):
        role, content = item.split("|||", 1)

        messages.append({
            "role": role,
            "content": content,
        })

    messages.append({
        "role": "user",
        "content": text,
    })

    response = llm_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        temperature=0.3,
    )

    answer = response.choices[0].message.content

    redis_client.lpush(history_key, f"user|||{text}")
    redis_client.lpush(history_key, f"assistant|||{answer}")

    redis_client.ltrim(history_key, 0, 20)

    return answer
