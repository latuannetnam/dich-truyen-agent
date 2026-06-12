import pytest

from dich_truyen_agent.browser_strategies import (
    NoopBrowserStrategy,
    get_browser_strategy,
)


def test_get_browser_strategy_returns_noop_for_missing_name() -> None:
    assert isinstance(get_browser_strategy(None), NoopBrowserStrategy)


def test_get_browser_strategy_returns_noop_for_explicit_name() -> None:
    assert isinstance(get_browser_strategy("noop"), NoopBrowserStrategy)


def test_get_browser_strategy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown crawl browser strategy"):
        get_browser_strategy("missing_strategy")
