"""tkinter Canvas に直接描く時系列折れ線グラフ.

外部ライブラリ（matplotlib 等）に依存しないので、PyInstaller で作る exe が小さい。
配色・目盛り計算は :mod:`proc_cpu_monitor.plotmath` にある（GUI なしでテスト可能）。
"""

from __future__ import annotations

import tkinter as tk
from collections import deque

from .plotmath import (
    BG,
    FG,
    FG_DIM,
    GRID,
    GRID_STRONG,
    PLOT_BG,
    SERIES_COLORS,
    format_percent,
    nice_ceiling,
)


class TimeSeriesChart(tk.Canvas):
    """右端が最新の、横スクロールする折れ線グラフ."""

    PAD_LEFT = 62
    PAD_RIGHT = 14
    PAD_TOP = 14
    PAD_BOTTOM = 30

    def __init__(self, master, window_seconds: float = 120.0, **kwargs):
        super().__init__(master, background=BG, highlightthickness=0, **kwargs)
        self.window_seconds = window_seconds
        self.y_mode = "auto"          # "auto" | "fixed"
        self.y_fixed_max = 100.0
        self.y_unit = "%"
        self.series = []              # [(name, color)]
        self._visible = {}            # name -> bool
        self._times = deque()
        self._values = {}             # name -> deque
        self._max_points = 100000
        self.bind("<Configure>", lambda _e: self.redraw())

    # ------------------------------------------------------------------
    def set_series(self, names):
        """系列を設定し直す（データはクリア）."""
        self.series = [(n, SERIES_COLORS[i % len(SERIES_COLORS)])
                       for i, n in enumerate(names)]
        self._visible = {n: self._visible.get(n, True) for n in names}
        self._times.clear()
        self._values = {n: deque() for n in names}
        self.redraw()

    def color_of(self, name):
        for n, color in self.series:
            if n == name:
                return color
        return FG

    def set_visible(self, name, visible):
        self._visible[name] = bool(visible)
        self.redraw()

    def is_visible(self, name):
        return self._visible.get(name, True)

    def clear(self):
        self._times.clear()
        for values in self._values.values():
            values.clear()
        self.redraw()

    def add_point(self, timestamp: float, values: dict):
        self._times.append(timestamp)
        for name, series in self._values.items():
            series.append(float(values.get(name, 0.0)))
        self._trim(timestamp)

    def _trim(self, now: float):
        keep = self.window_seconds * 1.2 + 5
        while len(self._times) > 2 and (now - self._times[0]) > keep:
            self._times.popleft()
            for series in self._values.values():
                series.popleft()
        while len(self._times) > self._max_points:
            self._times.popleft()
            for series in self._values.values():
                series.popleft()

    # ------------------------------------------------------------------
    def stats(self, name):
        """(現在値, 平均, 最大) を表示中の時間窓について返す."""
        values = self._window_values(name)
        if not values:
            return 0.0, 0.0, 0.0
        return values[-1], sum(values) / len(values), max(values)

    def _window_values(self, name):
        series = self._values.get(name)
        if not series or not self._times:
            return []
        now = self._times[-1]
        start = now - self.window_seconds
        return [v for t, v in zip(self._times, series) if t >= start]

    def _plot_max(self):
        top = 0.0
        for name, _color in self.series:
            if not self.is_visible(name):
                continue
            values = self._window_values(name)
            if values:
                top = max(top, max(values))
        return top

    def current_y_max(self):
        if self.y_mode == "fixed":
            return max(self.y_fixed_max, 1.0)
        return nice_ceiling(self._plot_max() * 1.15, minimum=100.0)

    # ------------------------------------------------------------------
    def redraw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 80 or height < 60:
            return

        left, right = self.PAD_LEFT, width - self.PAD_RIGHT
        top, bottom = self.PAD_TOP, height - self.PAD_BOTTOM
        if right <= left or bottom <= top:
            return

        self.create_rectangle(left, top, right, bottom, fill=PLOT_BG, outline=GRID_STRONG)

        y_max = self.current_y_max()
        self._draw_y_axis(left, right, top, bottom, y_max)
        self._draw_x_axis(left, right, top, bottom)

        if not self._times:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="計測待ち…", fill=FG_DIM, font=("Yu Gothic UI", 11))
            return

        now = self._times[-1]
        start = now - self.window_seconds
        span_x = right - left
        span_y = bottom - top

        def to_xy(t, v):
            x = right - (now - t) / self.window_seconds * span_x
            y = bottom - min(v, y_max) / y_max * span_y
            return x, max(top, y)

        for name, color in self.series:
            if not self.is_visible(name):
                continue
            series = self._values.get(name)
            if not series:
                continue

            # 1 ピクセルに複数点が来る場合は最大値でまとめる（スパイクを潰さずに軽くする）
            buckets = {}
            for t, v in zip(self._times, series):
                if t < start:
                    continue
                x = right - (now - t) / self.window_seconds * span_x
                key = int(x)
                current = buckets.get(key)
                if current is None or v > current[1]:
                    buckets[key] = (x, v)
            if not buckets:
                continue

            coords = []
            for x, v in buckets.values():
                coords.extend((x, bottom - min(v, y_max) / y_max * span_y))
            if len(coords) >= 4:
                self.create_line(*coords, fill=color, width=2,
                                 joinstyle="round", capstyle="round", smooth=False)
            last_x, last_y = to_xy(now, series[-1])
            self.create_oval(last_x - 3, last_y - 3, last_x + 3, last_y + 3,
                             fill=color, outline=BG)

    def _draw_y_axis(self, left, right, top, bottom, y_max):
        divisions = 5
        for i in range(divisions + 1):
            value = y_max * i / divisions
            y = bottom - (bottom - top) * i / divisions
            if i:
                self.create_line(left + 1, y, right - 1, y, fill=GRID)
            self.create_text(left - 8, y, text=f"{format_percent(value)}{self.y_unit}",
                             anchor="e", fill=FG_DIM, font=("Consolas", 9))

    def _draw_x_axis(self, left, right, top, bottom):
        divisions = 6
        window = self.window_seconds
        for i in range(divisions + 1):
            x = left + (right - left) * i / divisions
            seconds_ago = window * (1 - i / divisions)
            if 0 < i < divisions:
                self.create_line(x, top + 1, x, bottom - 1, fill=GRID)
            label = "現在" if seconds_ago < 0.5 else f"-{seconds_ago:.0f}s"
            self.create_text(x, bottom + 14, text=label, fill=FG_DIM,
                             font=("Consolas", 9))
