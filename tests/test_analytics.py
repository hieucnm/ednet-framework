# tests/test_analytics.py

import pytest
from unittest.mock import MagicMock, patch
from modules.analytics.kpi_engine import KPIEngine


@pytest.fixture
def engine():
    return KPIEngine()


def make_session(scalar_values: dict):
    """
    Helper: create a mock session where each successive
    execute().scalar() call returns the next value in the list.
    """
    session = MagicMock()
    scalars = iter(scalar_values)

    def mock_execute(*args, **kwargs):
        result = MagicMock()
        result.scalar.return_value = next(scalars, 0)
        result.fetchall.return_value = []
        result.rowcount = 0
        return result

    session.execute.side_effect = mock_execute
    return session


def test_k01_full_participation(engine):
    session = make_session(iter([8, 8]))  # total=8, active=8
    val = engine.k01_participation_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == 100.0


def test_k01_partial_participation(engine):
    session = make_session(iter([8, 6]))  # total=8, active=6
    val = engine.k01_participation_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == pytest.approx(75.0)


def test_k05_completion_rate(engine):
    session = make_session(iter([100, 80]))  # total=100, passed=80
    val = engine.k05_program_completion_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == pytest.approx(80.0)


def test_k05_no_enrollments(engine):
    session = make_session(iter([0, 0]))
    val = engine.k05_program_completion_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == 0.0


def test_k06_withdrawal_rate(engine):
    session = make_session(iter([100, 8]))  # total=100, withdrawn=8
    val = engine.k06_withdrawal_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == pytest.approx(8.0)


def test_k10_full_compliance(engine):
    session = make_session(iter([50, 50]))  # total=50, passed=50
    val = engine.k10_ethics_compliance_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == pytest.approx(100.0)


def test_k10_no_logs_returns_100(engine):
    session = make_session(iter([0, 0]))
    val = engine.k10_ethics_compliance_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == 100.0   # no logs = nothing failed


def test_k08_growth_rate(engine):
    session = make_session(iter([6, 2]))  # 6 at start, 2 joined
    val = engine.k08_member_growth_rate(
        session, 1, "2023-01-01", "2024-12-31"
    )
    assert val == pytest.approx(33.33, rel=1e-2)