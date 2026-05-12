def normalize_browser_target(target):
    if target.startswith("http"):
        return target

    if "." not in target:
        return f"https://www.{target}.com"

    return f"https://{target}"


def build_x_search_url(keyword):
    return "https://x.com/search?q=" + keyword.replace(" ", "%20") + "&src=typed_query"
