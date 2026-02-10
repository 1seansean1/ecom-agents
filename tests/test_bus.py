"""Tests for the Redis Streams message bus (src/bus.py).

These tests use the real Redis at localhost:6381 (Docker).
Run with: pytest tests/test_bus.py -v
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
import redis

# Ensure test Redis URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6381/0")

from src.bus import (
    ALL_STREAMS,
    CONSUMER_GROUP,
    STREAM_HUMAN_INBOUND,
    STREAM_SYSTEM_HEALTH,
    STREAM_TOWER_EVENTS,
    STREAM_TOWER_TICKETS,
    ack,
    claim_stale,
    ensure_consumer_groups,
    pending_count,
    publish,
    read_batch,
    read_multi,
)

# Use unique stream prefix per test run to avoid cross-test pollution
_TEST_PREFIX = f"test:{uuid.uuid4().hex[:8]}:"


def _r() -> redis.Redis:
    return redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


@pytest.fixture(autouse=True)
def _skip_if_no_redis():
    """Skip all tests if Redis is not available."""
    try:
        _r().ping()
    except (redis.ConnectionError, redis.TimeoutError):
        pytest.skip("Redis not available at localhost:6381")


class TestPublish:
    """Test publish() function."""

    def test_publish_returns_entry_id(self):
        entry_id = publish(
            STREAM_TOWER_EVENTS,
            "run.queued",
            {"run_id": "test_123", "status": "queued"},
            source="test",
        )
        assert entry_id is not None
        assert isinstance(entry_id, str)
        assert "-" in entry_id  # Redis stream IDs are "timestamp-seq"

    def test_publish_message_content(self):
        r = _r()
        msg_id = uuid.uuid4().hex[:16]
        publish(
            STREAM_TOWER_EVENTS,
            "run.started",
            {"run_id": "test_456", "status": "running"},
            source="test",
            msg_id=msg_id,
        )

        # Read the last entry from the stream
        entries = r.xrevrange(STREAM_TOWER_EVENTS, count=1)
        assert len(entries) > 0
        _, fields = entries[0]
        assert fields["msg_type"] == "run.started"
        assert fields["msg_id"] == msg_id
        assert fields["source"] == "test"

        payload = json.loads(fields["payload"])
        assert payload["run_id"] == "test_456"
        assert payload["status"] == "running"

    def test_publish_to_different_streams(self):
        for stream in [STREAM_TOWER_EVENTS, STREAM_TOWER_TICKETS, STREAM_SYSTEM_HEALTH]:
            entry_id = publish(stream, "test.event", {"test": True}, source="test")
            assert entry_id is not None

    def test_publish_fail_open_bad_data(self):
        """publish() should never raise, even with unusual data."""
        # Circular reference can't be JSON-serialized normally,
        # but default=str should handle it
        entry_id = publish(
            STREAM_TOWER_EVENTS,
            "test.failopen",
            {"obj": object()},
            source="test",
        )
        # Should still succeed because default=str handles non-serializable
        assert entry_id is not None


class TestConsumerGroups:
    """Test consumer group management."""

    def test_ensure_consumer_groups_idempotent(self):
        """Calling ensure_consumer_groups() twice should not raise."""
        ensure_consumer_groups()
        ensure_consumer_groups()  # second call should be fine

    def test_consumer_groups_created_for_all_streams(self):
        ensure_consumer_groups()
        r = _r()
        for stream in ALL_STREAMS:
            try:
                groups = r.xinfo_groups(stream)
                group_names = [g["name"] for g in groups]
                assert CONSUMER_GROUP in group_names
            except redis.ResponseError:
                # Stream might not exist yet if no messages published
                pass


class TestReadAndAck:
    """Test read_batch(), read_multi(), and ack()."""

    def test_read_batch_returns_published_message(self):
        ensure_consumer_groups()

        # Publish a unique message
        unique = uuid.uuid4().hex[:8]
        publish(
            STREAM_TOWER_EVENTS,
            f"test.read.{unique}",
            {"unique": unique},
            source="test",
        )

        # Read it back
        consumer_name = f"test-consumer-{unique}"
        batch = read_batch(STREAM_TOWER_EVENTS, consumer_name, count=100, block_ms=500)

        # Find our message
        found = False
        for entry_id, fields in batch:
            if fields.get("msg_type") == f"test.read.{unique}":
                found = True
                payload = json.loads(fields["payload"])
                assert payload["unique"] == unique
                # Ack it
                acked = ack(STREAM_TOWER_EVENTS, entry_id)
                assert acked >= 1
                break

        assert found, f"Published message test.read.{unique} not found in batch"

    def test_read_multi_reads_from_multiple_streams(self):
        ensure_consumer_groups()

        unique = uuid.uuid4().hex[:8]
        publish(STREAM_TOWER_EVENTS, f"test.multi.{unique}", {"s": "events"}, source="test")
        publish(STREAM_SYSTEM_HEALTH, f"test.multi.{unique}", {"s": "health"}, source="test")

        consumer_name = f"test-multi-{unique}"
        entries = read_multi(
            [STREAM_TOWER_EVENTS, STREAM_SYSTEM_HEALTH],
            consumer_name,
            count=100,
            block_ms=500,
        )

        streams_seen = set()
        for stream, entry_id, fields in entries:
            if fields.get("msg_type") == f"test.multi.{unique}":
                streams_seen.add(stream)
                ack(stream, entry_id)

        assert STREAM_TOWER_EVENTS in streams_seen
        assert STREAM_SYSTEM_HEALTH in streams_seen

    def test_ack_with_no_ids_returns_zero(self):
        result = ack(STREAM_TOWER_EVENTS)
        assert result == 0


class TestClaimStale:
    """Test claim_stale() for dead letter recovery."""

    def test_claim_stale_empty_returns_empty(self):
        ensure_consumer_groups()
        result = claim_stale(
            STREAM_TOWER_EVENTS,
            f"test-claimer-{uuid.uuid4().hex[:8]}",
            min_idle_ms=999_999_999,  # extremely long — nothing should match
            count=5,
        )
        assert isinstance(result, list)


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_publish_read_ack_cycle(self):
        """Full round-trip: publish → read → process → ack."""
        ensure_consumer_groups()

        unique = uuid.uuid4().hex[:8]
        publish(
            STREAM_TOWER_TICKETS,
            "ticket.created",
            {
                "ticket_id": 42,
                "run_id": f"run_{unique}",
                "ticket_type": "tool_call",
                "risk_level": "high",
                "tldr": "Test ticket",
            },
            source="test",
        )

        consumer_name = f"test-integration-{unique}"
        batch = read_batch(STREAM_TOWER_TICKETS, consumer_name, count=100, block_ms=500)

        processed = False
        for entry_id, fields in batch:
            if fields.get("msg_type") == "ticket.created":
                payload = json.loads(fields["payload"])
                if payload.get("run_id") == f"run_{unique}":
                    assert payload["ticket_id"] == 42
                    assert payload["risk_level"] == "high"
                    ack(STREAM_TOWER_TICKETS, entry_id)
                    processed = True
                    break

        assert processed, "Failed to process the published ticket message"

    def test_human_inbound_outbound(self):
        """Test publishing to holly:human:inbound."""
        ensure_consumer_groups()
        entry_id = publish(
            STREAM_HUMAN_INBOUND,
            "human.message",
            {"sender": "sean", "channel": "api", "body": "What's running?"},
            source="test",
        )
        assert entry_id is not None
