"""プロセス CPU モニター (Windows) の GUI 本体."""

from __future__ import annotations

import csv
import ctypes
import datetime as dt
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import config as cfg
from .chart import TimeSeriesChart
from .plotmath import BG, FG, FG_DIM, GRID_STRONG, PLOT_BG, format_percent
from .win_cpu import (
    IS_WINDOWS,
    ProcessCpuSampler,
    enable_debug_privilege,
    is_elevated,
    logical_processor_count,
)

APP_TITLE = "プロセス CPU モニター"
UI_FONT = ("Yu Gothic UI", 9)
UI_FONT_BOLD = ("Yu Gothic UI", 9, "bold")
MONO_FONT = ("Consolas", 9)

INTERVAL_CHOICES = [("0.5 秒", 500), ("1 秒", 1000), ("2 秒", 2000), ("5 秒", 5000)]
WINDOW_CHOICES = [("1 分", 60), ("2 分", 120), ("5 分", 300),
                  ("10 分", 600), ("30 分", 1800)]


def _enable_dpi_awareness() -> float:
    """高 DPI 対応。スケール係数 (96dpi=1.0) を返す."""
    if not IS_WINDOWS:
        return 1.0
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            return 1.0
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 90)  # LOGPIXELSY
        ctypes.windll.user32.ReleaseDC(0, dc)
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0


class MonitorApp:
    def __init__(self, root: tk.Tk, scale: float = 1.0):
        self.root = root
        self.scale = scale
        self.settings = cfg.load()
        self.cpu_count = logical_processor_count()
        self.elevated = is_elevated()
        self.debug_privilege = enable_debug_privilege() if IS_WINDOWS else False

        self.sampler = ProcessCpuSampler(self.settings["processes"])
        self.paused = False
        self._after_id = None
        self._next_tick = None
        self._start_monotonic = time.monotonic()
        self._csv_file = None
        self._csv_writer = None
        self._csv_path_display = ""
        self._last_samples = {}
        self._legend_rows = {}

        self._build_ui()
        self._apply_settings_to_widgets()
        self._rebuild_series()
        self._schedule(initial=True)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ UI
    def _px(self, value: int) -> int:
        return int(round(value * self.scale))

    def _build_ui(self):
        root = self.root
        root.title(APP_TITLE)
        root.configure(background=BG)
        root.minsize(self._px(760), self._px(420))

        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=FG, font=UI_FONT)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Dim.TLabel", foreground=FG_DIM)
        style.configure("TButton", background="#232b36", foreground=FG,
                        borderwidth=1, focusthickness=0, padding=(8, 3))
        style.map("TButton",
                  background=[("active", "#2f3a48"), ("pressed", "#3a4657")])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TCombobox", fieldbackground=PLOT_BG, background="#232b36",
                        foreground=FG, arrowcolor=FG, selectbackground=PLOT_BG,
                        selectforeground=FG)
        root.option_add("*TCombobox*Listbox.background", PLOT_BG)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", "#3a4657")

        # --- ツールバー -------------------------------------------------
        bar = ttk.Frame(root, padding=(self._px(8), self._px(6)))
        bar.pack(side="top", fill="x")

        ttk.Label(bar, text="更新間隔").pack(side="left")
        self.var_interval = tk.StringVar()
        self.cmb_interval = ttk.Combobox(
            bar, textvariable=self.var_interval, state="readonly", width=6,
            values=[label for label, _ in INTERVAL_CHOICES])
        self.cmb_interval.pack(side="left", padx=(self._px(4), self._px(12)))
        self.cmb_interval.bind("<<ComboboxSelected>>", self.on_interval_changed)

        ttk.Label(bar, text="表示期間").pack(side="left")
        self.var_window = tk.StringVar()
        self.cmb_window = ttk.Combobox(
            bar, textvariable=self.var_window, state="readonly", width=6,
            values=[label for label, _ in WINDOW_CHOICES])
        self.cmb_window.pack(side="left", padx=(self._px(4), self._px(12)))
        self.cmb_window.bind("<<ComboboxSelected>>", self.on_window_changed)

        ttk.Label(bar, text="縦軸").pack(side="left")
        self.var_yaxis = tk.StringVar()
        self.y_choices = [
            ("自動", "auto"),
            ("0-100%", "fixed100"),
            (f"0-{self.cpu_count * 100}% (全コア)", "fixedmax"),
        ]
        self.cmb_yaxis = ttk.Combobox(
            bar, textvariable=self.var_yaxis, state="readonly", width=16,
            values=[label for label, _ in self.y_choices])
        self.cmb_yaxis.pack(side="left", padx=(self._px(4), self._px(12)))
        self.cmb_yaxis.bind("<<ComboboxSelected>>", self.on_yaxis_changed)

        self.var_normalize = tk.BooleanVar(value=bool(self.settings["normalize"]))
        ttk.Checkbutton(bar, text=f"コア数({self.cpu_count})で割る",
                        variable=self.var_normalize,
                        command=self.on_normalize_changed).pack(side="left")

        self.var_topmost = tk.BooleanVar(value=bool(self.settings["topmost"]))
        ttk.Checkbutton(bar, text="最前面", variable=self.var_topmost,
                        command=self.on_topmost_changed).pack(
            side="left", padx=(self._px(8), 0))

        self.btn_settings = ttk.Button(bar, text="プロセス設定…",
                                       command=self.open_process_dialog)
        self.btn_settings.pack(side="right")
        self.btn_csv = ttk.Button(bar, text="CSV記録", command=self.toggle_csv)
        self.btn_csv.pack(side="right", padx=self._px(4))
        self.btn_clear = ttk.Button(bar, text="クリア", command=self.clear_data)
        self.btn_clear.pack(side="right", padx=self._px(4))
        self.btn_pause = ttk.Button(bar, text="一時停止", command=self.toggle_pause)
        self.btn_pause.pack(side="right", padx=self._px(4))

        # --- 本体 -------------------------------------------------------
        body = ttk.Frame(root)
        body.pack(side="top", fill="both", expand=True,
                  padx=self._px(8), pady=(0, self._px(4)))

        self.chart = TimeSeriesChart(body, window_seconds=self.settings["window_seconds"],
                                     ui_scale=self.scale)
        self.chart.PAD_LEFT = self._px(TimeSeriesChart.PAD_LEFT)
        self.chart.PAD_RIGHT = self._px(TimeSeriesChart.PAD_RIGHT)
        self.chart.PAD_TOP = self._px(TimeSeriesChart.PAD_TOP)
        self.chart.PAD_BOTTOM = self._px(TimeSeriesChart.PAD_BOTTOM)
        self.chart.pack(side="left", fill="both", expand=True)

        self.legend = tk.Frame(body, background=BG, width=self._px(250))
        self.legend.pack(side="right", fill="y", padx=(self._px(8), 0))
        self.legend.pack_propagate(False)

        # --- ステータスバー ---------------------------------------------
        status = tk.Frame(root, background=PLOT_BG)
        status.pack(side="bottom", fill="x")
        self.lbl_status = tk.Label(status, text="", background=PLOT_BG,
                                   foreground=FG_DIM, font=UI_FONT, anchor="w")
        self.lbl_status.pack(side="left", padx=self._px(8), pady=self._px(3))
        self.lbl_status_right = tk.Label(status, text="", background=PLOT_BG,
                                         foreground=FG_DIM, font=UI_FONT, anchor="e")
        self.lbl_status_right.pack(side="right", padx=self._px(8), pady=self._px(3))
        self._update_status()

    def _apply_settings_to_widgets(self):
        # 設定ファイルに想定外の値が入っていた場合は既定値に丸める
        if self.settings["interval_ms"] not in [ms for _, ms in INTERVAL_CHOICES]:
            self.settings["interval_ms"] = INTERVAL_CHOICES[1][1]
        if self.settings["window_seconds"] not in [sec for _, sec in WINDOW_CHOICES]:
            self.settings["window_seconds"] = WINDOW_CHOICES[1][1]
        if self.settings["y_mode"] not in [key for _, key in self.y_choices]:
            self.settings["y_mode"] = "auto"
        self.chart.window_seconds = self.settings["window_seconds"]

        interval = self.settings["interval_ms"]
        self.var_interval.set(next(label for label, ms in INTERVAL_CHOICES
                                   if ms == interval))
        window = self.settings["window_seconds"]
        self.var_window.set(next(label for label, sec in WINDOW_CHOICES
                                 if sec == window))
        y_mode = self.settings["y_mode"]
        self.var_yaxis.set(next(label for label, key in self.y_choices
                                if key == y_mode))
        self._apply_y_mode(y_mode)
        self.root.attributes("-topmost", bool(self.settings["topmost"]))

    # ------------------------------------------------- 凡例 (右パネル)
    def _rebuild_series(self):
        names = self.settings["processes"]
        self.sampler.set_names(names)
        self.chart.set_series(names)
        for child in self.legend.winfo_children():
            child.destroy()
        self._legend_rows = {}

        tk.Label(self.legend, text="プロセス", background=BG, foreground=FG,
                 font=UI_FONT_BOLD, anchor="w").pack(fill="x", pady=(self._px(4), self._px(2)))

        for name in names:
            color = self.chart.color_of(name)
            row = tk.Frame(self.legend, background=PLOT_BG,
                           highlightbackground=GRID_STRONG, highlightthickness=1)
            row.pack(fill="x", pady=self._px(3))

            head = tk.Frame(row, background=PLOT_BG)
            head.pack(fill="x", padx=self._px(6), pady=(self._px(5), 0))
            swatch = tk.Canvas(head, width=self._px(12), height=self._px(12),
                               background=PLOT_BG, highlightthickness=0)
            swatch.create_rectangle(0, self._px(3), self._px(12), self._px(9),
                                    fill=color, outline=color)
            swatch.pack(side="left")
            var = tk.BooleanVar(value=True)
            chk = tk.Checkbutton(
                head, text=name, variable=var, background=PLOT_BG, foreground=FG,
                activebackground=PLOT_BG, activeforeground=FG, selectcolor=BG,
                font=UI_FONT_BOLD, anchor="w", padx=self._px(4), borderwidth=0,
                highlightthickness=0,
                command=lambda n=name, v=var: self.chart.set_visible(n, v.get()))
            chk.pack(side="left", fill="x", expand=True)

            value_lbl = tk.Label(row, text="--", background=PLOT_BG, foreground=color,
                                 font=("Consolas", 16), anchor="w")
            value_lbl.pack(fill="x", padx=self._px(8))
            detail_lbl = tk.Label(row, text="", background=PLOT_BG, foreground=FG_DIM,
                                  font=MONO_FONT, anchor="w", justify="left",
                                  wraplength=self._px(228))
            detail_lbl.pack(fill="x", padx=self._px(8), pady=(0, self._px(6)))

            self._legend_rows[name] = (value_lbl, detail_lbl, var)

        note = ("表示値はパフォーマンスモニターの "
                "Process \\ % Processor Time と同じ定義です"
                f"（コア数で割らない場合の最大は {self.cpu_count * 100}%）。")
        tk.Label(self.legend, text=note, background=BG, foreground=FG_DIM,
                 font=("Yu Gothic UI", 8), anchor="w", justify="left",
                 wraplength=self._px(238)).pack(
            fill="x", side="bottom", pady=self._px(6))

    # ------------------------------------------------------------- 計測
    def _schedule(self, initial=False):
        """次の計測を予約する（after の誤差が蓄積しないよう補正する）."""
        interval = self.settings["interval_ms"] / 1000.0
        now = time.monotonic()
        if initial or self._next_tick is None:
            self._next_tick = now
        else:
            self._next_tick += interval
            # スリープ復帰や間隔変更で大きくずれたら基準を取り直す
            if not (now - interval <= self._next_tick <= now + interval * 2):
                self._next_tick = now + interval
        delay = max(0, int((self._next_tick - now) * 1000))
        self._after_id = self.root.after(delay, self._tick)

    def _tick(self):
        self._after_id = None
        if not self.paused:
            try:
                self._do_sample()
            except Exception as exc:  # 計測失敗でアプリを落とさない
                self.lbl_status_right.config(text=f"計測エラー: {exc}")
        self._schedule()

    def _do_sample(self):
        samples = self.sampler.sample()
        self._last_samples = samples
        now = time.monotonic()
        divisor = self.cpu_count if self.var_normalize.get() else 1

        plotted = {}
        for name, sample in samples.items():
            plotted[name] = sample.percent / divisor
        if any(s.valid for s in samples.values()):
            self.chart.add_point(now, plotted)
        self.chart.redraw()
        self._update_legend(samples, plotted)
        self._update_status()
        self._write_csv(samples)

    def _update_legend(self, samples, plotted):
        unit = "%"
        for name, (value_lbl, detail_lbl, _var) in self._legend_rows.items():
            sample = samples.get(name)
            current, average, peak = self.chart.stats(name)
            if sample is None or sample.instances == 0:
                value_lbl.config(text="停止中")
                detail_lbl.config(text="プロセスが起動していません")
                continue
            value_lbl.config(text=f"{format_percent(plotted.get(name, 0.0))}{unit}")
            lines = [
                f"平均 {format_percent(average)}{unit}  最大 {format_percent(peak)}{unit}",
                f"インスタンス {sample.instances} / PID {', '.join(str(p) for p in sample.pids[:4])}"
                + (" …" if len(sample.pids) > 4 else ""),
            ]
            if sample.access_denied:
                lines.append(f"⚠ {sample.access_denied} 個は権限不足（管理者で実行）")
            detail_lbl.config(text="\n".join(lines))

    def _update_status(self):
        mode = "コア数で正規化 (タスクマネージャー相当)" if self.var_normalize.get() \
            else "% Processor Time (perfmon 相当)"
        admin = "管理者" if self.elevated else "通常ユーザー"
        parts = [f"論理コア {self.cpu_count}", admin, mode]
        if not IS_WINDOWS:
            parts.append("※ Windows 以外では計測できません")
        self.lbl_status.config(text="　|　".join(parts))
        right = []
        if self.paused:
            right.append("一時停止中")
        if self._csv_file is not None:
            right.append(f"CSV記録中: {self._csv_path_display}")
        right.append(dt.datetime.now().strftime("%H:%M:%S"))
        self.lbl_status_right.config(text="　|　".join(right))

    # ------------------------------------------------------------ 操作
    def on_interval_changed(self, _event=None):
        label = self.var_interval.get()
        for text, ms in INTERVAL_CHOICES:
            if text == label:
                self.settings["interval_ms"] = ms
                break
        cfg.save(self.settings)
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._schedule(initial=True)

    def on_window_changed(self, _event=None):
        label = self.var_window.get()
        for text, seconds in WINDOW_CHOICES:
            if text == label:
                self.settings["window_seconds"] = seconds
                self.chart.window_seconds = seconds
                break
        cfg.save(self.settings)
        self.chart.redraw()
        self._update_legend(self._last_samples, self._current_plotted())

    def on_yaxis_changed(self, _event=None):
        label = self.var_yaxis.get()
        for text, key in self.y_choices:
            if text == label:
                self.settings["y_mode"] = key
                self._apply_y_mode(key)
                break
        cfg.save(self.settings)
        self.chart.redraw()

    def _apply_y_mode(self, key):
        if key == "fixed100":
            self.chart.y_mode = "fixed"
            self.chart.y_fixed_max = 100.0
        elif key == "fixedmax":
            self.chart.y_mode = "fixed"
            self.chart.y_fixed_max = 100.0 if self.var_normalize.get() \
                else float(self.cpu_count * 100)
        else:
            self.chart.y_mode = "auto"

    def on_normalize_changed(self):
        self.settings["normalize"] = bool(self.var_normalize.get())
        cfg.save(self.settings)
        self.chart.clear()
        self.sampler.reset()
        self._apply_y_mode(self.settings["y_mode"])
        self.chart.redraw()
        self._update_status()

    def on_topmost_changed(self):
        self.settings["topmost"] = bool(self.var_topmost.get())
        cfg.save(self.settings)
        self.root.attributes("-topmost", self.settings["topmost"])

    def toggle_pause(self):
        self.paused = not self.paused
        self.btn_pause.config(text="再開" if self.paused else "一時停止")
        if not self.paused:
            self.sampler.reset()
        self._update_status()

    def clear_data(self):
        self.chart.clear()
        self.sampler.reset()

    def _current_plotted(self):
        divisor = self.cpu_count if self.var_normalize.get() else 1
        return {n: s.percent / divisor for n, s in self._last_samples.items()}

    # -------------------------------------------------------------- CSV
    def toggle_csv(self):
        if self._csv_file is not None:
            self._stop_csv()
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="CSV の保存先",
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile="cpu_%s.csv" % dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
        if not path:
            return
        try:
            self._csv_file = open(path, "w", newline="", encoding="utf-8-sig")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"CSV を開けません:\n{exc}", parent=self.root)
            self._csv_file = None
            return
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow(
            ["timestamp"]
            + [f"{name} % Processor Time" for name in self.settings["processes"]]
            + [f"{name} instances" for name in self.settings["processes"]])
        self._csv_path_display = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self.btn_csv.config(text="記録停止")
        self._update_status()

    def _write_csv(self, samples):
        if self._csv_writer is None:
            return
        names = self.settings["processes"]
        row = [dt.datetime.now().isoformat(timespec="milliseconds")]
        row += [f"{samples[n].percent:.3f}" if n in samples else "" for n in names]
        row += [samples[n].instances if n in samples else "" for n in names]
        try:
            self._csv_writer.writerow(row)
            self._csv_file.flush()
        except (OSError, ValueError):
            self._stop_csv()

    def _stop_csv(self):
        if self._csv_file is not None:
            try:
                self._csv_file.close()
            except OSError:
                pass
        self._csv_file = None
        self._csv_writer = None
        self.btn_csv.config(text="CSV記録")
        self._update_status()

    # -------------------------------------------------- プロセス設定
    def open_process_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("監視するプロセス")
        dialog.configure(background=BG)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        tk.Label(dialog, text="1 行に 1 つ、実行ファイル名を入力してください（例: sldworks.exe）",
                 background=BG, foreground=FG, font=UI_FONT, anchor="w",
                 justify="left").pack(fill="x", padx=self._px(12), pady=(self._px(12), self._px(6)))
        text = tk.Text(dialog, width=44, height=8, background=PLOT_BG, foreground=FG,
                       insertbackground=FG, font=MONO_FONT, relief="flat",
                       highlightthickness=1, highlightbackground=GRID_STRONG)
        text.pack(padx=self._px(12))
        text.insert("1.0", "\n".join(self.settings["processes"]))
        text.focus_set()

        buttons = ttk.Frame(dialog, padding=(self._px(12), self._px(10)))
        buttons.pack(fill="x")

        def apply_and_close():
            names, seen = [], set()
            for line in text.get("1.0", "end").splitlines():
                name = line.strip()
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    names.append(name)
            if not names:
                messagebox.showwarning(APP_TITLE, "1 つ以上入力してください。", parent=dialog)
                return
            self.settings["processes"] = names
            cfg.save(self.settings)
            self.sampler.close()
            self._rebuild_series()
            self._stop_csv()
            dialog.destroy()

        ttk.Button(buttons, text="OK", command=apply_and_close).pack(side="right")
        ttk.Button(buttons, text="キャンセル", command=dialog.destroy).pack(
            side="right", padx=self._px(6))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    # ------------------------------------------------------------ 終了
    def on_close(self):
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self._stop_csv()
        self.sampler.close()
        cfg.save(self.settings)
        self.root.destroy()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    scale = _enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", scale * 96 / 72)
    except tk.TclError:
        pass
    root.geometry(f"{int(1040 * scale)}x{int(620 * scale)}")
    app = MonitorApp(root, scale=scale)
    root.app = app  # GC 防止
    if not IS_WINDOWS:
        messagebox.showwarning(
            APP_TITLE,
            "このアプリは Windows 専用です。\n"
            "Windows 以外では CPU 使用率は 0 のまま表示されます。",
            parent=root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
