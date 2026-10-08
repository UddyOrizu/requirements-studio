"""UUIDv7 (RFC 9562) row ids: time-ordered, so B-tree inserts stay local. Python 3.12 has no uuid.uuid7."""
import os
import time
import uuid


def uuid7() -> uuid.UUID:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10))
    value = (ms & (2**48 - 1)) << 80  # 48-bit unix ms timestamp
    value |= 0x7 << 76  # version
    value |= ((rand >> 62) & 0xFFF) << 64  # 12 random bits
    value |= 0b10 << 62  # variant
    value |= rand & (2**62 - 1)  # 62 random bits
    return uuid.UUID(int=value)


def uuid7_str() -> str:
    return str(uuid7())
