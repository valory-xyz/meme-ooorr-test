import json
import os

import dotenv
import requests
from openai import OpenAI


dotenv.load_dotenv(override=True)


def openai_call():
    """Call through OpenAI"""
    client = OpenAI(
        base_url=os.getenv("OPENAI_API_BASE"), api_key=os.getenv("OPENAI_API_KEY")
    )

    completion = client.completions.create(
        model="accounts/sentientfoundation/models/dobby-mini-unhinged-llama-3-1-8b",
        prompt="Write a tweet about memecoins",
    )
    print(completion.choices[0].text)


def api_call():
    """Call through API"""
    url = "https://api.fireworks.ai/inference/v1/chat/completions"
    payload = {
        "model": "accounts/sentientfoundation/models/dobby-mini-unhinged-llama-3-1-8b",
        "max_tokens": 16384,
        "top_p": 1,
        "top_k": 40,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "temperature": 0.6,
        "messages": [{"role": "user", "content": "Write a tweet about memecoins"}],
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
    }
    response = requests.request(
        "POST", url, headers=headers, data=json.dumps(payload), timeout=60
    )
    print(response.json()["choices"][0]["message"]["content"])


api_call()
