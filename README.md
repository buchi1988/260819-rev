# プロセス CPU モニター (Windows)

指定したプロセスの CPU 使用率を **リアルタイムで折れ線グラフ表示** する Windows デスクトップアプリです。
表示値はパフォーマンスモニターの **`Process \ % Processor Time`** と同じ定義で計算しています。

初期の監視対象:

- `sldworks.exe` （SOLIDWORKS）
- `EdmServerV6.exe` （SOLIDWORKS PDM / EPDM サーバー）
- `ENOPLMCSAClient.exe` （3DEXPERIENCE / ENOVIA クライアント）

監視対象はアプリ上の **［プロセス設定…］** からいつでも追加・変更できます（設定は自動保存）。

---

## 1. exe の入手

### A. 自分でビルドする（Windows 上、推奨）

1. Python 3.9 以降をインストール（<https://www.python.org/downloads/windows/> 、インストーラで **Add python.exe to PATH** にチェック）
2. このリポジトリを ZIP でダウンロードして展開、または `git clone`
3. **`build.bat`** をダブルクリック
4. `dist\ProcCpuMonitor.exe` が出来上がります

`EdmServerV6.exe` のようにサービス／別ユーザーとして動くプロセスも確実に計測したい場合は、
代わりに **`build-admin.bat`** を実行してください（起動時に UAC で管理者権限を要求する
`dist\ProcCpuMonitor-Admin.exe` が生成されます）。

PowerShell から直接叩く場合:

```powershell
.\build.ps1          # 通常版
.\build.ps1 -Admin   # 管理者権限を要求する版
```

生成される exe は **単一ファイル・インストール不要**（約 10 MB）で、Python が入っていない
別の PC にコピーしてもそのまま動きます。

### B. GitHub Actions のビルド成果物を使う

このリポジトリに push すると、`Windows exe をビルド` ワークフローが windows-latest 上で
テスト → ビルド → 起動確認まで行い、`ProcCpuMonitor-exe` という成果物（通常版・管理者版の
両方の exe）を添付します。GitHub の **Actions** タブ → 該当の実行 → **Artifacts** から
ダウンロードできます。

---

## 2. 画面と操作

```
┌──────────────────────────────────────────────────────────┬──────────────┐
│ 更新間隔 [1 秒▼] 表示期間 [2 分▼] 縦軸 [自動▼] □コア数で割る  │  プロセス    │
├──────────────────────────────────────────────────────────┤  ■ sldworks  │
│  800% ┤                                            ╭──   │    142.35%   │
│  600% ┤                          ╭─────╮          ╭╯     │  平均 88.10% │
│  400% ┤            ╭────╮       ╭╯     ╰──────────╯      │  最大 412.5% │
│  200% ┤   ╭────────╯    ╰───────╯                        │  インスタンス │
│    0% ┼───┴────┴────┴────┴────┴────┴────┴────┴────┴──    │  1 / PID 9312│
│      -2分   -1分40s  -1分20s  -1分   -40s   -20s    現在   │  ■ EdmServer…│
└──────────────────────────────────────────────────────────┴──────────────┘
 論理コア 16 ｜ 管理者 ｜ % Processor Time (perfmon 相当)          12:34:56
```

| 操作 | 内容 |
| --- | --- |
| 更新間隔 | 0.5 / 1 / 2 / 5 秒。パフォーマンスモニター既定値と同じにするなら 1 秒 |
| 表示期間 | 横軸の長さ（1 / 2 / 5 / 10 / 30 分）。目盛りは期間に応じた刻みで自動的に振られる |
| 縦軸 | 自動 ／ 0-100% 固定 ／ 0-(論理コア数×100)% 固定 |
| コア数で割る | ON にするとタスクマネージャーの「CPU」列と同じスケールになる（既定は OFF＝perfmon 相当） |
| 最前面 | ウィンドウを常に手前に表示 |
| 一時停止／再開 | 計測の停止・再開 |
| クリア | グラフの履歴を消去 |
| CSV記録 | 1 サンプルごとに CSV へ追記（時刻・各プロセスの % Processor Time・インスタンス数） |
| プロセス設定… | 監視対象の実行ファイル名を 1 行 1 つで編集 |
| 凡例のチェックボックス | 系列の表示／非表示を切り替え |

凡例には **現在値・表示期間内の平均・最大・インスタンス数・PID** を表示します。
対象が起動していない場合は「停止中」と表示され、起動すると自動的に計測が始まります。

---

## 3. 計測方法（パフォーマンスモニターとの対応）

`% Processor Time` は「そのプロセスが単位時間あたりに消費したプロセッサ時間の割合」です。
本アプリは Windows API を直接使い、perfmon と同じ式で算出しています。

```
% Processor Time = (カーネル時間 + ユーザー時間 の増分) ÷ 経過時間 × 100
```

- `CreateToolhelp32Snapshot` で対象プロセス名の PID をすべて列挙
- 各 PID を `OpenProcess` し `GetProcessTimes` でカーネル時間・ユーザー時間（100ns 単位）を取得
- 前回サンプルとの差分を、`QueryPerformanceCounter` 相当の高精度時計で測った経過時間で割る

重要な点:

- **論理コア数では割りません。** perfmon の `Process \ % Processor Time` と同じく、
  最大値は `論理コア数 × 100%` です（16 コアなら 1600%）。
  タスクマネージャーの「CPU」列はこれをコア数で割った値なので、
  合わせたいときは［コア数で割る］を ON にしてください。
- **同名プロセスが複数ある場合は合計値**を表示します
  （perfmon で `sldworks`, `sldworks#1`, … を足したものに相当）。インスタンス数も凡例に出ます。
- プロセスが終了・再起動しても PID を追い直すので、グラフはそのまま継続します
  （PID 再利用はプロセス生成時刻で判別しています）。
- 最初の 1 サンプルは差分が取れないため 0% になります（perfmon と同じ挙動）。

### 管理者権限について

自分と同じユーザーで動いているプロセス（通常 `sldworks.exe` や `ENOPLMCSAClient.exe`）は
通常権限のままで計測できます。
一方、**サービスや別ユーザーとして動作しているプロセス**（`EdmServerV6.exe` が典型）は
アクセス権不足で読めないことがあります。その場合、

- 凡例に `⚠ n 個は権限不足（管理者で実行）` と表示されます
- `ProcCpuMonitor-Admin.exe`（`build-admin.bat` で生成）を使うか、
  通常版 exe を右クリック →［管理者として実行］してください

管理者で起動した場合はアプリが自動で SeDebugPrivilege を有効化します。

---

## 4. 設定と CSV

- 設定ファイル: `%APPDATA%\ProcCpuMonitor\config.json`
  （監視プロセス一覧・更新間隔・表示期間・縦軸モードなどを自動保存）
- CSV: ［CSV記録］で保存先を選ぶと、以降 1 サンプルごとに追記されます。
  Excel でそのまま開けるよう UTF-8 BOM 付きで出力します。
  値は **コア数で割らない生の % Processor Time** です（画面の表示設定に影響されません）。

CSV の例:

```csv
timestamp,sldworks.exe % Processor Time,EdmServerV6.exe % Processor Time,...,sldworks.exe instances,...
2026-08-19T12:34:56.123,142.350,3.010,0.000,1,1,0
```

---

## 5. 開発

外部ライブラリへの依存はありません（GUI は Python 標準の tkinter、グラフは Canvas への自前描画、
計測は ctypes による Win32 API 呼び出し）。exe 化のときだけ PyInstaller を使います。

```powershell
python -m proc_cpu_monitor        # src を PYTHONPATH に入れて実行する場合
python main.py                    # そのまま実行
python -m pytest tests -q         # テスト
```

### ファイル構成

| パス | 内容 |
| --- | --- |
| `main.py` | エントリポイント（PyInstaller のビルド対象） |
| `src/proc_cpu_monitor/win_cpu.py` | Win32 API による % Processor Time サンプラ |
| `src/proc_cpu_monitor/chart.py` | tkinter Canvas 折れ線グラフ |
| `src/proc_cpu_monitor/plotmath.py` | 目盛り計算・配色（GUI 非依存） |
| `src/proc_cpu_monitor/app.py` | GUI 本体 |
| `src/proc_cpu_monitor/config.py` | 設定の保存／読み込み |
| `build.ps1` / `build.bat` / `build-admin.bat` | exe ビルド |
| `tests/` | ロジックテスト＋GUI スモークテスト |

### 制限事項

- Windows 専用です（計測に Win32 API を使用）。他 OS では起動はしますが値は 0 のままです。
- 32bit / 64bit の別なく計測できますが、64bit プロセスを計測する場合は 64bit の Python で
  ビルドした exe を使ってください（通常の Python 公式インストーラは 64bit です）。
