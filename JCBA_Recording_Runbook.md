# JCBA インターネットサイマルラジオ 自動録音 Runbook

**作成日**: 2026-04-27  
**最終更新**: 2026-04-30（OGGStitcher導入・再接続ギャップ解消・CDNノード二重化対応）  
**対象環境**: Windows 10/11、Python 3.x  
**対象局・日程**:

| 日時 | 局名 | station_id | 録音時間 |
|---|---|---|---|
| 2026/04/30 12:30〜13:00 | 富山シティエフエム | `toyamacityfm` | 30分 |
| 2026/05/01 13:00〜14:00 | ラジオたかおか | `radiotakaoka` | 60分 |
| 2026/05/02 12:00〜12:30 | FMとなみ | `fmtonami` | 30分 |

---

## 1. アーキテクチャ概要

```
[jcbasimul.com]
     │
     ▼
GET /api/select_stream?station={station_id}&channel=0&quality=high&burst={burst}
     │   burst=5（初回のみ）/ burst=2（再接続時）
     │
     │ Response (JSON)
     │   code: 200
     │   location: wss://os1308.radimo.smen.biz:443/socket?burst={burst}
     │   token: JWT (有効期限 約15秒)
     │
     ▼
WebSocket 接続 (wss://)
     │ サブプロトコル: listener.fmplapla.com
     │ 接続直後に token をテキストメッセージとして送信
     │
     ▼
バイナリ受信（OGG/Opus）→ OGGStitcher へ
     │
     │  OGGStitcher:
     │   ・OGGページ単位でパース
     │   ・granule_position をserial番号別に追跡
     │   ・burst=2 による約2.1秒オーバーラップから重複ページを除去
     │   → 再接続ギャップなし（シームレス）でファイルへ書き込み
     │
     │ ※ tokenは約9秒ごとに自動再取得・再接続（burst=2で再接続）
     ▼
録音完了 → C:\RadioRec\{station_id}_{YYYYMMDD}_{HHMM}.ogg
```

**重要**: 旧来の `musicbird-hls.leanstream.co` (HLS/m3u8) は廃止済み。  
現在は **Radimo** (WebSocket + OGG/Opusコーデック) に移行している。

### CDNノードの二重化

jcbasimul.com は2つのCDNノードを運用しており、接続のたびに切替が起きる場合がある。各ノードは異なる `serial_number` を使用し、**granule値が約3.7時間分（約6.46億サンプル）ずれている**。OGGStitcher は serial番号をキーとする辞書で granule を追跡するため、ノード切替があっても正常に動作する。

---

## 2. ファイル構成

```
C:\RadioRec\
├── jcba_rec.py              # 録音コアスクリプト (Python)
├── rec_toyamacityfm.bat     # 富山シティエフエム 録音バッチ
├── rec_radiotakaoka.bat     # ラジオたかおか 録音バッチ
├── rec_fmtonami.bat         # FMとなみ 録音バッチ
├── register_tasks.bat       # タスクスケジューラ一括登録
├── install_libs.bat         # Pythonライブラリインストール
├── rec_log.txt              # 録音ログ (自動生成)
└── *.ogg                    # 録音済みファイル (自動生成)
```

---

## 3. 初回セットアップ手順

### 3-1. Python のインストール

1. https://www.python.org/downloads/ からインストーラーをダウンロード
2. インストール時に **「Add Python to PATH」に必ずチェック**
3. インストール後、コマンドプロンプトで確認:

```
python --version
```

### 3-2. ファイルの配置

全ファイルを `C:\RadioRec\` に保存する（フォルダがなければ新規作成）。

### 3-3. Pythonライブラリのインストール

`install_libs.bat` をダブルクリックして実行。または手動で:

```
pip install requests websocket-client
```

### 3-4. 動作テスト（必須）

コマンドプロンプトで以下を実行:

```
python C:\RadioRec\jcba_rec.py fmtonami 30 C:\RadioRec\test.ogg
```

期待される出力例:

```
[fmtonami] Start recording 30s -> C:\RadioRec\test.ogg
[fmtonami] elapsed=0s   ws_window=9s  recv=0KB    skip=0pg
[fmtonami] elapsed=9s   ws_window=9s  recv=120KB  skip=7pg
[fmtonami] elapsed=18s  ws_window=9s  recv=240KB  skip=14pg
[fmtonami] Done. Total recv=360KB  Pages written=XXX  skipped=21  File=C:\RadioRec\test.ogg
```

- `skip=Npg` は OGGStitcher が除去した重複ページの累計数。1接続ごとに約7増加するのが正常。

30秒後に `test.ogg` が作成され、VLC Player で再生して音が出ることを確認する。

### 3-5. タスクスケジューラへの登録

`register_tasks.bat` を**右クリック → 「管理者として実行」**。

登録確認コマンド:

```
SCHTASKS /QUERY /TN "RadioRec_ToyamaCityFM_0430"
SCHTASKS /QUERY /TN "RadioRec_Takaoka_0501"
SCHTASKS /QUERY /TN "RadioRec_FMTonami_0502"
```

---

## 4. 録音中の動作仕様

### jcba_rec.py の動作フロー

```
1. GET /api/select_stream?station={id}&channel=0&quality=high&burst={burst}
      └─ location (WSS URL) と token (JWT) を取得
         初回: burst=5（5秒バッファ付き）
         再接続: burst=2（2秒バッファ → OGGStitcher が重複除去）

2. JWT の exp フィールドから有効期限を計算
      └─ 有効期限 - TOKEN_MARGIN(5秒) = WebSocket 接続維持時間（約9秒）
         ※ PREFETCH_BEFORE=1 により窓終了1秒前から次トークンをバックグラウンド取得

3. WebSocket 接続（サブプロトコル: listener.fmplapla.com）
      └─ 接続直後に token をテキストメッセージとして送信

4. バイナリデータ（OGG/Opus）を受信 → OGGStitcher 経由でファイルへ書き込み
      └─ OGGStitcher が granule 重複ページを除去し、シームレスな音声を保証

5. 有効期限5秒前に WebSocket を閉じ、burst=2 で 1〜4 を繰り返す

6. 合計録音時間に達したら終了
```

### token のリフレッシュ間隔

| パラメータ | 値 |
|---|---|
| token 有効期限 | 約15秒（exp - iat = 15） |
| リフレッシュタイミング | 有効期限の5秒前（= 約9〜10秒ごと） |
| 定数 `TOKEN_MARGIN` | `5`（秒）← jcba_rec.py 内で変更可 |
| 定数 `PREFETCH_BEFORE` | `1`（秒）← 窓終了1秒前にバックグラウンド取得開始 |
| 実効 ws_window | 約9秒（= 15 - TOKEN_MARGIN - PREFETCH_BEFORE） |
| 初回 burst | `5`（秒）|
| 再接続時 burst | `2`（秒、= `RECONNECT_BURST`）|
| 1接続あたりのオーバーラップ | 約2.1秒（7ページ × 300ms/ページ）|

---

## 5. 出力ファイル

| 項目 | 内容 |
|---|---|
| コンテナ形式 | OGG (`.ogg`) |
| コーデック | **Opus**（旧Vorbisから変更済み） |
| ファイル名 | `{station_id}_{YYYYMMDD}_{HHMM}.ogg` |
| 例 | `fmtonami_20260502_1200.ogg` |
| 再生 | VLC Player 推奨（https://www.videolan.org/） |

> **注意**: コーデックが Vorbis ではなく **Opus** になっている。VLC は両方対応しているので問題なく再生できる。

---

## 6. PC の電源管理

録音はPCがON状態でないと実行されない。以下を事前に設定すること:

- **シャットダウン禁止**（スリープはOK）
- 設定 → 電源とスリープ → スリープを「なし」または十分長い時間に設定
- タスクスケジューラ → 「全般」タブ → 「ユーザーがログオンしているかどうかにかかわらず実行する」を選択

---

## 7. ログの確認

`C:\RadioRec\rec_log.txt` に録音の開始・終了と Python の詳細出力がすべて記録される:

```
[2026/04/30 12:30:01.23] START toyamacityfm
[toyamacityfm] Start recording 1800s -> C:\RadioRec\toyamacityfm_20260430_1230.ogg
[toyamacityfm] elapsed=0s   ws_window=9s  recv=0KB    skip=0pg
[toyamacityfm] elapsed=9s   ws_window=9s  recv=120KB  skip=7pg
[toyamacityfm] elapsed=18s  ws_window=9s  recv=240KB  skip=14pg
...
[toyamacityfm] Token fetch error: ... -- retrying in 5s   ← エラー時はここに記録される
...
[toyamacityfm] Done. Total recv=21600KB  Pages written=6000  skipped=1400  File=C:\RadioRec\toyamacityfm_20260430_1230.ogg
[2026/04/30 13:00:04.56] END   toyamacityfm
```

- `ws_window=9s`: 正常値は約9秒。大幅に短い場合は PREFETCH_BEFORE の値を確認。
- `skip=Npg`: 接続回数 × 7 程度が正常。0のままなら burst=RECONNECT_BURST が効いていない可能性。

録音が途中で止まった場合は `rec_log.txt` の `Token fetch error:` や `WS error:` を確認すること。

---

## 8. トラブルシューティング

### `400 Client Error: Bad Request`

**原因**: API パラメーター不足。旧バージョンのスクリプトを使用している。

**対処**: `jcba_rec.py` を最新版（`channel=0&quality=high&burst={burst}` 付き）に差し替える。

```
# 正しいAPI呼び出し形式
GET /api/select_stream?station=fmtonami&channel=0&quality=high&burst=5
```

### `WS error: Handshake status 404 Not Found`

**原因**: WebSocket 接続時にサブプロトコルが指定されていない。

**対処**: `jcba_rec.py` を最新版（`subprotocols=["listener.fmplapla.com"]` 付き）に差し替える。

### 音声がループしている・同じ箇所が繰り返される

**原因**: 再接続のたびに `burst=5` が送られ、過去5秒分の音声が重複して録音される。

**対処**: `jcba_rec.py` を最新版（初回のみ `burst=5`、再接続時は `burst=0`）に差し替える。

### 録音が途中で止まる

**原因**: トークン再取得時にネットワークエラーが発生し、スクリプトが例外終了していた。

**対処**: `jcba_rec.py` を最新版（`fetch_token` に try/except + 5秒リトライ）に差し替える。次回からエラー発生時もリトライして録音を継続する。エラー内容は `rec_log.txt` に `Token fetch error:` として記録される。

### 録音ファイルが空・極端に小さい

| 確認項目 | 対処 |
|---|---|
| ネットワーク接続 | インターネット接続を確認 |
| API エラー | コマンドプロンプトで手動実行してエラーメッセージを確認 |
| token 取得失敗 | ブラウザで `https://www.jcbasimul.com/fmtonami` を開いて再生できるか確認 |

### `python` コマンドが見つからない

```
'python' は、内部コマンドまたは外部コマンド...として認識されていません
```

Python インストール時に「Add Python to PATH」のチェックが漏れている。  
Python を再インストールするか、環境変数 PATH に Python のフォルダを手動追加する。

### `ModuleNotFoundError: No module named 'websocket'`

```
pip install websocket-client
```

`websocket` ではなく **`websocket-client`** をインストールすること。

### OGG ファイルが再生できない

VLC Player（https://www.videolan.org/）をインストールして再生する。  
Windows Media Player では標準では再生できないため注意。

### ログの `skip=0pg` が増えない（OGGStitcher が機能していない）

**確認**: `jcba_rec.py` の `RECONNECT_BURST` が `2` 以上になっているか確認する。`burst=0` のままだとオーバーラップがないため skip が増えない（かつギャップが残る）。

### ログの `ws_window` が7秒以下になっている

**原因**: `PREFETCH_BEFORE` が大きすぎる。バックグラウンド取得したトークンは `PREFETCH_BEFORE` 秒後に使われるため、その分だけ有効期限が縮む。

**対処**: `PREFETCH_BEFORE = 1` に設定する（実効窓 = 15 - 5 - 1 = 9秒）。

### 録音ファイルの途中で音声が数秒間抜ける（ログに `skip` が急増している）

**原因**: CDNノードが切り替わり、granule値が大きく異なるノードからの音声が誤って除去された可能性がある。旧バージョン（`_last_granule` が辞書でなく整数）のスクリプトを使用している。

**対処**: `jcba_rec.py` を最新版（`_last_granule` が `{}` の辞書）に差し替える。

---

## 9. クリーンアップ

録音完了後、タスクスケジューラから削除する:

```
SCHTASKS /DELETE /TN "RadioRec_ToyamaCityFM_0430" /F
SCHTASKS /DELETE /TN "RadioRec_Takaoka_0501" /F
SCHTASKS /DELETE /TN "RadioRec_FMTonami_0502" /F
```

---

## 10. 別の局を録音したい場合

### station_id の調べ方

`https://www.jcbasimul.com/{station_id}` の URL スラッグがそのまま station_id になる。

| URL | station_id |
|---|---|
| https://www.jcbasimul.com/fmtonami | `fmtonami` |
| https://www.jcbasimul.com/toyamacityfm | `toyamacityfm` |
| https://www.jcbasimul.com/radiotakaoka | `radiotakaoka` |

全局一覧: https://www.jcbasimul.com/

### 手動録音コマンド

```
python C:\RadioRec\jcba_rec.py {station_id} {秒数} {出力ファイルパス}
```

例（FMとなみを30分録音）:

```
python C:\RadioRec\jcba_rec.py fmtonami 1800 C:\RadioRec\fmtonami_test.ogg
```

### 新しいタスクを追加する場合

```
SCHTASKS /CREATE /TN "RadioRec_{任意名}" /TR "C:\RadioRec\{batファイル名}" /SC ONCE /SD {YYYY/MM/DD} /ST {HH:MM} /F
```

---

## 11. 依存関係

| 種別 | 名前 | バージョン | 用途 |
|---|---|---|---|
| ランタイム | Python | 3.8 以上 | スクリプト実行環境 |
| Pythonライブラリ | `requests` | 最新 | REST API 呼び出し |
| Pythonライブラリ | `websocket-client` | 最新 | WebSocket 接続・受信 |
| 再生ソフト | VLC Player | 最新 | OGGファイルの再生 |

---

## 12. 参考情報

| 項目 | 値 |
|---|---|
| JCBA サイト | https://www.jcbasimul.com/ |
| プレーヤー実装 | `/player/player-ui.min.js`（Radimo製 Web Components） |
| stream API | `GET https://www.jcbasimul.com/api/select_stream?station={id}&channel=0&quality=high&burst={n}` |
| WebSocket | `wss://os1308.radimo.smen.biz:443/socket?burst={n}`（動的に変わる可能性あり） |
| WSサブプロトコル | `listener.fmplapla.com` |
| 音声形式 | OGG/Opus（JWT の `sub` フィールド: `/fmtonami/0/high.ogg`） |
| token 認証 | JWT (RS256)、WebSocket 接続直後に最初のメッセージとして送信 |
| burst パラメータ | 初回=5（秒バッファ）、再接続=0（重複防止） |

---

## 13. 変更履歴

| 日付 | 変更内容 |
|---|---|
| 2026-04-27 | 初版作成 |
| 2026-04-27 | API仕様変更対応: `channel`, `quality`, `burst` パラメーター追加（400エラー修正） |
| 2026-04-27 | WebSocket サブプロトコル `listener.fmplapla.com` 追加（404エラー修正） |
| 2026-04-27 | 再接続時 `burst=0` 対応（音声ループ修正） |
| 2026-04-27 | 音声コーデック Vorbis → Opus に記述更新 |
| 2026-04-29 | `fetch_token` 例外時リトライ追加（録音途切れ修正） |
| 2026-04-29 | `rec_*.bat` に `>> rec_log.txt 2>&1` 追加（詳細ログ） |
| 2026-04-29 | `CLAUDE.md` 作成（Claudeセッション引き継ぎ用） |
| 2026-04-30 | OGGStitcher 導入（granule追跡による再接続ギャップ解消） |
| 2026-04-30 | `RECONNECT_BURST=2` 導入（再接続時に2秒オーバーラップ取得） |
| 2026-04-30 | `PREFETCH_BEFORE=3→1` 変更（実効ws_windowを9秒に回復） |
| 2026-04-30 | OGGStitcher の `_last_granule` を辞書化（CDNノード二重化対応） |
| 2026-04-30 | ログ形式を `burst=X` → `skip=Xpg` に変更 |
