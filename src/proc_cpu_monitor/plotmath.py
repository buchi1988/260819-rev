"""グラフ描画に使う純粋な計算・配色（tkinter に依存しない）."""

from __future__ import annotations

BG = "#12161c"
PLOT_BG = "#171d26"
GRID = "#2a3340"
GRID_STRONG = "#3a4657"
FG = "#c8d2e0"
FG_DIM = "#7c8899"

# 系列の色（コントラスト高めで見分けやすい並び）
SERIES_COLORS = [
    "#4ea1ff",  # 青
    "#ffb64d",  # 橙
    "#5fd08c",  # 緑
    "#e06c9f",  # ピンク
    "#b58cff",  # 紫
    "#f2f0a1",  # 黄
]

_NICE_STEPS = (1, 2, 2.5, 5, 10)


def nice_ceiling(value: float, minimum: float = 100.0) -> float:
    """目盛りとしてキリの良い上限値を返す."""
    value = max(value, minimum)
    exp = 1.0
    while exp * 10 <= value:
        exp *= 10
    while exp > value:
        exp /= 10
    for step in _NICE_STEPS:
        candidate = step * exp
        if candidate >= value:
            return candidate
    return 10 * exp


def format_percent(value: float) -> str:
    """桁数をそろえた % 表示."""
    if value >= 1000:
        return f"{value:.0f}"
    if value >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}"
