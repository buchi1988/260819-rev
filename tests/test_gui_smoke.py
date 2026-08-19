"""GUI を実際に起動するスモークテスト（tkinter と画面が使える環境でのみ実行）."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pytest  # noqa: E402

tk = pytest.importorskip("tkinter")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # 画面のない環境
        pytest.skip(f"ディスプレイなし: {exc}")
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


def test_chart_draws_without_error(root):
    from proc_cpu_monitor.chart import TimeSeriesChart

    chart = TimeSeriesChart(root, window_seconds=60, width=600, height=300)
    chart.pack()
    chart.set_series(["a.exe", "b.exe"])
    root.update()
    for i in range(30):
        chart.add_point(i, {"a.exe": i * 3.0, "b.exe": 100 + i})
    chart.redraw()
    root.update()
    assert chart.current_y_max() >= 129
    current, average, peak = chart.stats("b.exe")
    assert current == pytest.approx(129.0)
    assert peak == pytest.approx(129.0)
    assert 100 <= average <= 129

    chart.set_visible("b.exe", False)
    chart.redraw()
    chart.clear()
    assert chart.stats("a.exe") == (0.0, 0.0, 0.0)


def test_app_starts_samples_and_closes(root):
    from proc_cpu_monitor.app import MonitorApp

    app = MonitorApp(root)
    root.update()
    for _ in range(3):
        app._do_sample()
        root.update()
    assert set(app._last_samples) == set(app.settings["processes"])

    # 主要な操作が例外を出さないこと
    app.var_normalize.set(True)
    app.on_normalize_changed()
    app.var_window.set("5 分")
    app.on_window_changed()
    app.var_yaxis.set(app.y_choices[2][0])
    app.on_yaxis_changed()
    app.var_interval.set("2 秒")
    app.on_interval_changed()
    app.toggle_pause()
    app.toggle_pause()
    app.clear_data()
    root.update()

    app.settings["processes"] = ["explorer.exe"]
    app.sampler.close()
    app._rebuild_series()
    app._do_sample()
    root.update()

    app.on_close()
