import json
import os
import uuid

import pytest
from redis.asyncio import Redis

from services.common.events import EventEnvelope
from services.common.outbox import EventOutbox, enqueue_event, relay_outbox

REDIS_URL = os.environ.get("RS_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="RS_REDIS_URL not set")


@pytest.fixture
async def redis():
    r = Redis.from_url(REDIS_URL)
    yield r
    await r.aclose()


async def test_db_outbox_relay_publishes_once(sessionmaker, redis):
    stream = f"rs:test:{uuid.uuid4().hex}"
    event = EventEnvelope(type="ir.patched", process_id="proc_relay", ir_version=2, correlation_id="corr-relay",
                          payload={"patch_id": "p", "from_version": 1, "to_version": 2, "changed_paths": ["/nodes"]})
    async with sessionmaker() as s:
        await enqueue_event(s, event)
        await s.commit()
    try:
        while await relay_outbox(sessionmaker, redis, stream=stream):
            pass
        entries = await redis.xrange(stream)
        ours = [f for _, f in entries if f[b"event_id"] == str(event.event_id).encode()]
        assert len(ours) == 1
        assert ours[0][b"type"] == b"ir.patched"
        assert EventEnvelope.model_validate(json.loads(ours[0][b"event"])) == event
        async with sessionmaker() as s:
            assert (await s.get(EventOutbox, event.event_id)).published_at is not None
        assert await relay_outbox(sessionmaker, redis, stream=stream) == 0  # nothing left to publish
    finally:
        await redis.delete(stream)
