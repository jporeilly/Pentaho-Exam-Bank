"""Tests for the EventBus class."""

import pytest
from exam_bank.gui.state import EventBus


class TestEventBus:
    def test_on_and_emit(self):
        bus = EventBus()
        results = []
        bus.on("test", lambda: results.append("called"))
        bus.emit("test")
        assert results == ["called"]

    def test_multiple_handlers(self):
        bus = EventBus()
        results = []
        bus.on("test", lambda: results.append("a"))
        bus.on("test", lambda: results.append("b"))
        bus.emit("test")
        assert results == ["a", "b"]

    def test_off_removes_handler(self):
        bus = EventBus()
        results = []
        handler = lambda: results.append("called")
        bus.on("test", handler)
        bus.off("test", handler)
        bus.emit("test")
        assert results == []

    def test_emit_unknown_event(self):
        bus = EventBus()
        bus.emit("nonexistent")  # Should not raise

    def test_duplicate_registration_ignored(self):
        bus = EventBus()
        results = []
        handler = lambda: results.append("called")
        bus.on("test", handler)
        bus.on("test", handler)  # duplicate
        bus.emit("test")
        assert results == ["called"]  # only once

    def test_emit_many(self):
        bus = EventBus()
        results = []
        bus.on("a", lambda: results.append("a"))
        bus.on("b", lambda: results.append("b"))
        bus.emit_many("a", "b")
        assert results == ["a", "b"]

    def test_emit_with_kwargs(self):
        bus = EventBus()
        results = []
        bus.on("test", lambda x=0: results.append(x))
        bus.emit("test", x=42)
        assert results == [42]

    def test_handler_error_does_not_break_others(self):
        bus = EventBus()
        results = []
        bus.on("test", lambda: 1/0)  # will raise
        bus.on("test", lambda: results.append("ok"))
        bus.emit("test")
        assert results == ["ok"]  # second handler still runs
