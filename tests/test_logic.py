"""GUI を起動しないロジックのテスト（Linux でも実行可）."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

from proc_cpu_monitor import config  # noqa: E402
from proc_cpu_monitor.win_cpu import (  # noqa: E402
    IS_WINDOWS,
    ProcessCpuSampler,
    logical_processor_count,
)


def test_nice_ceiling_never_below_100():
    from proc_cpu_monitor.plotmath import nice_ceiling

    assert nice_ceiling(0) == 100
    assert nice_ceiling(45) == 100
    assert nice_ceiling(100) == 100


@pytest.mark.parametrize("value,expected", [
    (101, 200), (150, 200), (210, 250), (260, 500), (900, 1000), (1100, 2000),
])
def test_nice_ceiling_steps(value, expected):
    from proc_cpu_monitor.plotmath import nice_ceiling

    assert nice_ceiling(value) == expected


def test_format_percent():
    from proc_cpu_monitor.plotmath import format_percent

    assert format_percent(0) == "0.00"
    assert format_percent(12.345) == "12.35"
    assert format_percent(123.456) == "123.5"
    assert format_percent(1234.5) == "1234"


def test_sampler_first_sample_is_invalid():
    sampler = ProcessCpuSampler(["sldworks.exe", "EdmServerV6.exe"])
    first = sampler.sample()
    assert set(first) == {"sldworks.exe", "EdmServerV6.exe"}
    assert all(not s.valid for s in first.values())
    second = sampler.sample()
    assert all(s.valid for s in second.values())
    assert all(s.percent >= 0 for s in second.values())
    sampler.close()


def test_sampler_matches_running_python_on_windows():
    """自分自身 (python.exe) を監視して 0 以上の値が返ることを確認."""
    if not IS_WINDOWS:
        pytest.skip("Windows 専用")
    import time

    exe = os.path.basename(sys.executable)
    sampler = ProcessCpuSampler([exe])
    sampler.sample()
    deadline = time.time() + 0.5
    while time.time() < deadline:  # CPU を回す
        pass
    result = sampler.sample()[exe]
    sampler.close()
    assert result.instances >= 1
    assert result.percent > 10  # 0.5 秒間ビジーループしたので十分大きいはず
    assert result.percent <= logical_processor_count() * 100 + 5


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    data = config.load()
    assert data["processes"] == config.DEFAULT_PROCESSES
    data["processes"] = ["a.exe", "b.exe"]
    data["interval_ms"] = 2000
    config.save(data)
    assert config.load()["processes"] == ["a.exe", "b.exe"]
    assert config.load()["interval_ms"] == 2000


def test_config_rejects_empty_process_list(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save({"processes": []})
    assert config.load()["processes"] == config.DEFAULT_PROCESSES


@pytest.mark.parametrize("window,expected_step", [
    (60, 10), (120, 20), (300, 60), (600, 120), (1800, 300),
])
def test_time_step(window, expected_step):
    from proc_cpu_monitor.plotmath import time_step

    assert time_step(window) == expected_step


@pytest.mark.parametrize("seconds,expected", [
    (0, "現在"), (10, "-10s"), (59, "-59s"),
    (60, "-1分"), (300, "-5分"), (90, "-1分30s"), (1800, "-30分"),
])
def test_format_age(seconds, expected):
    from proc_cpu_monitor.plotmath import format_age

    assert format_age(seconds) == expected


def test_x_axis_labels_fit_in_window():
    """目盛りが表示期間を超えず、末尾がちょうど窓の端に来ること."""
    from proc_cpu_monitor.plotmath import time_step

    for window in (60, 120, 300, 600, 1800):
        step = time_step(window)
        ticks = []
        age = 0.0
        while age <= window + 0.001:
            ticks.append(age)
            age += step
        assert ticks[-1] == pytest.approx(window)
        assert 5 <= len(ticks) <= 9
