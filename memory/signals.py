import hashlib

from config.clients import redis_client


SIGNAL_MEMORY_PREFIX = "signal_memory:"
SIGNAL_MEMORY_TTL_SECONDS = 60 * 60 * 24 * 7


def signal_hash(text):
    raw = (text or "").strip().lower()
    raw = " ".join(raw.split())
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def filter_new_signals(keyword, text):
    key = SIGNAL_MEMORY_PREFIX + keyword.lower().strip()

    blocks = []
    current = []

    for line in text.splitlines():
        if line.strip():
            current.append(line)
        else:
            if current:
                blocks.append("\n".join(current))
                current = []

    if current:
        blocks.append("\n".join(current))

    new_blocks = []

    for block in blocks:
        if len(block) < 40:
            continue

        h = signal_hash(block)

        if not redis_client.sismember(key, h):
            redis_client.sadd(key, h)
            new_blocks.append(block)

    redis_client.expire(key, SIGNAL_MEMORY_TTL_SECONDS)

    return "\n\n---\n\n".join(new_blocks[:20])
