import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import twikit


def tweet_to_json(tweet: Any) -> Dict:
    """Tweet to json"""
    return {
        "id": tweet.id,
        "user_name": tweet.user.name,
        "text": tweet.text,
        "created_at": tweet.created_at,
        "view_count": tweet.view_count,
        "retweet_count": tweet.retweet_count,
        "quote_count": tweet.quote_count,
        "view_count_state": tweet.view_count_state,
    }


async def get_tweets():
    """Get tweets"""

    with open(Path("twikit_cookies.json"), "r", encoding="utf-8") as cookies_file:
        cookies = json.load(cookies_file)

        client = twikit.Client(language="en-US")
        client.set_cookies(cookies)

        user = await client.get_user_by_screen_name(screen_name="percebot")

        tweets = await client.get_user_tweets(
            user_id=user.id, tweet_type="Tweets", count=1
        )

        return [tweet_to_json(t) for t in tweets]


tweets = asyncio.run(get_tweets())
date = datetime.strptime(tweets[0]["created_at"], "%a %b %d %H:%M:%S %z %Y")
print(date)
