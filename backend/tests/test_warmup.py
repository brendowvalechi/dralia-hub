"""Testes unitários do warm-up manager — não precisa de banco."""
import pytest
from app.services.warmup_manager import (
    advance_warmup_day,
    calculate_health_delta,
    clamp_health,
    get_warmup_limit,
    is_warmed_up,
)


def test_warmup_limits():
    assert get_warmup_limit(1) == 20
    assert get_warmup_limit(3) == 20
    assert get_warmup_limit(4) == 50
    assert get_warmup_limit(7) == 50
    assert get_warmup_limit(8) == 100
    assert get_warmup_limit(14) == 100
    assert get_warmup_limit(15) == 200
    assert get_warmup_limit(22) == 300
    assert get_warmup_limit(31) == 300


def test_advance_warmup_day():
    assert advance_warmup_day(1) == 2
    assert advance_warmup_day(29) == 30
    assert advance_warmup_day(30) is None  # Completo
    assert advance_warmup_day(None) is None


def test_is_warmed_up():
    assert is_warmed_up(None) is True
    assert is_warmed_up(30) is False
    assert is_warmed_up(31) is True


def test_health_delta_low_delivery():
    delta = calculate_health_delta(sent=100, delivered=50, failed=5, read=0)
    assert delta < 0


def test_health_delta_high_delivery():
    delta = calculate_health_delta(sent=100, delivered=85, failed=2, read=0)
    assert delta > 0


def test_health_delta_with_reads():
    delta_no_read = calculate_health_delta(sent=100, delivered=85, failed=2, read=0)
    delta_with_read = calculate_health_delta(sent=100, delivered=85, failed=2, read=25)
    assert delta_with_read > delta_no_read


def test_clamp_health():
    assert clamp_health(150) == 100
    assert clamp_health(-10) == 0
    assert clamp_health(75) == 75


def test_health_zero_sent():
    delta = calculate_health_delta(sent=0, delivered=0, failed=0, read=0)
    assert delta == 0
