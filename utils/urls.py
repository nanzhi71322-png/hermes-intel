import os
from urllib.parse import quote_plus


def normalize_browser_target(target):
    if target.startswith("http"):
        return target

    if "." not in target:
        return f"https://www.{target}.com"

    return f"https://{target}"


def build_x_search_url(keyword):
    instances = os.getenv(
        "NITTER_INSTANCES",
        "https://nitter.tiekoetter.com,https://nitter.privacyredirect.com,https://nitter.net",
    )
    instance = instances.split(",", 1)[0].strip().rstrip("/")
    query = quote_plus(keyword)

    return f"{instance}/search?f=tweets&q={query}"
