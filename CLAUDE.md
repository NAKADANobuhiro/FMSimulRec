# CLAUDE.md — FMSimulRec プロジェクト コンテキスト

このファイルは Claude がセッションをまたいでプロジェクトを理解するためのメモです。

---

## プロジェクト概要

**目的**: JCBAインターネットサイマルラジオ（https://www.jcbasimul.com/）の指定局を、Windowsタスクスケジューラで自動録音する。

**対象局（2026年録音予定）**:

| 日時 | 局名 | station_id |
|---|---|---|
| 2026/04/30 12:30〜13:00 | 富山シティエフエム | `toyamacityfm` |
| 2026/05/01 13:00〜14:00 | ラジオたかおか | `radiotakaoka` |
| 2026/05/02 12:00〜12:30 | FMとなみ | `fmtonami` |

**GitHub**: https://github.com/NAKADANobuhiro/FMSimulRec

---

## 技術的経緯（重要）

### jcbasimul.com の現行API仕様（2026年4月時点）

サイトはNext.js + Radimo（Musicbird製 Web Components）で構成されている。

#### トークン取得API

```
GET https://www.jcbasimul.com/api/select_stream
    ?station={station_id}
    &channel=0
    &quality=high
    &burst={burst}
```

- `channel=0`, `quality=high`, `burst` の3パラメーターが必須（旧: `station` のみ）
- `burst`: 初回接続=5（秒バッファ）、再接続=2（2秒バッファ → OGGStitcher が重複除去）
- レスポンス: `{"code":200, "location":"wss://...", "token":"JWT..."}`
- JWT有効期限: 約15秒（exp - iat = 15）

#### WebSocket接続

```
wss://os1308.radimo.smen.biz:443/socket?burst={burst}
サブプロトコル: listener.fmplapla.com   ← 必須（ないと 404）
```

- 接続直後にJWTトークンをテキストメッセージとして送信
- バイナリデータ（OGG/Opusコーデック）をそのまま受信・ファイル書き込み
- player-ui.min.js（`/player/player-ui.min.js`）に実装の全詳細あり

#### 音声フォーマット

- コンテナ: OGG
- コーデック: **Opus**（旧サービスのVorbisから変更済み）
- JWT sub フィールド: `/fmtonami/0/high.ogg`
- VLCで再生可能

### 過去に発生したバグと修正

| エラー | 原因 | 修正 |
|---|---|---|
| `400 Bad Request` | `channel`, `quality`, `burst` パラメーター不足 | SELECT_STREAM URL に追加 |
| `WS error: 404 Not Found` | WebSocket サブプロトコル未指定 | `subprotocols=["listener.fmplapla.com"]` 追加 |
| 音声がループする | 再接続のたびに `burst=5` → 過去5秒分が重複 | 再接続時は `burst=0` に変更（後に burst=2 + OGGStitcher方式に再設計） |
| 20分で録音が途切れる | `fetch_token` 例外でスクリプト終了 | try/except + 5秒待ちリトライを追加 |
| 再接続のたびに約0.9秒の無音ギャップ | WebSocketハンドシェイク＋サーバー起動時間による音声欠落 | OGGStitcher導入 + burst=2 で2.1秒オーバーラップ取得し重複除去 |
| OGGStitcher がCDNノード切替時に全音声をブロック | 2つのCDNノード（異なるserial番号）がgranuleの基準点を約3.7時間分ずらして使用。単一カーソルでは切替後の全ページが「重複」と判定された | `_last_granule` を `serial → granule` の辞書に変更し、serial番号ごとに独立追跡 |
| PREFETCH_BEFORE=3 でWebSocket窓が7秒に短縮 | バックグラウンド取得したトークンが3秒後に使用されるため、exp基準で窓が縮む | PREFETCH_BEFORE=1 に変更 → 実効窓 ≈ 9秒 |

---

## ファイル構成

```
FMSimulRec/
├── jcba_rec.py              # 録音コアスクリプト（Python）
├── rec_toyamacityfm.bat     # 富山シティエフエム 録音バッチ
├── rec_radiotakaoka.bat     # ラジオたかおか 録音バッチ
├── rec_fmtonami.bat         # FMとなみ 録音バッチ
├── register_tasks.bat       # タスクスケジューラ一括登録
├── register_test.bat        # テスト用タスク登録（単局）
├── install_libs.bat         # Pythonライブラリインストール
├── README.md                # セットアップガイド（エンドユーザー向け）
├── JCBA_Recording_Runbook.md # 詳細技術Runbook
├── CLAUDE.md                # このファイル
└── .gitignore
```

---

## jcba_rec.py の主要定数

```python
TOKEN_MARGIN    = 5   # トークン期限切れN秒前に接続を閉じる
PREFETCH_BEFORE = 1   # WebSocket窓終了N秒前に次トークンをバックグラウンド取得開始
                      #   → 実効ws_window ≈ 15 - 5 - 1 = 9秒
RECONNECT_BURST = 2   # 再接続時のburst秒数（2秒 = 7ページ × 300ms のオーバーラップ）
                      #   → OGGStitcher が重複ページを除去してシームレス録音
CONNECT_TIMEOUT = 10  # WebSocket接続タイムアウト（秒）
FETCH_RETRY_WAIT = 5  # トークン取得失敗時のリトライ待機（秒）
```

### OGGStitcher の動作原理

再接続時に `burst=RECONNECT_BURST` で取得した音声は、前の接続と約2.1秒オーバーラップする。
OGGStitcher はこれを活用してギャップを埋める:

1. 受信バイト列をバッファリングし、OGGページ単位でパース
2. 各ページの `granule_position`（絶対タイムスタンプ）と `serial_number` を読み取る
3. serial番号ごとに「最後に書き込んだgranule」を記録（`_last_granule[serial]`）
4. `granule > last_granule[serial]` のページのみファイルに書き込み、重複は破棄
5. BOS（ストリーム開始）ページと granule=0/MAX64 のヘッダーページは常に書き込む

### CDNノードの二重化について

jcbasimul.com は2つのCDNノードを使用しており、接続先が切り替わることがある。

- 各ノードは異なる `serial_number`（例: `ab9c0b35`、`b5e1c3eb`）を使用
- **両ノードのgranule値は約6.46億サンプル（≈3.7時間）ずれている**
- 単一の `_last_granule` カーソルを使うと、高いgranuleのノードを一度でも経由した後は、低いgranuleのノードからの全ページが「重複」と誤判定される
- `_last_granule` を serial番号をキーとする辞書にすることでこれを解決

---

## 依存ライブラリ

```
pip install requests websocket-client
```

Python標準ライブラリのみで動作する部分はそのまま。ffmpegは不使用。

---

## ログ

`C:\RadioRec\rec_log.txt` にSTART/ENDとPythonの標準出力がすべて記録される。  
バッチファイルが `>> rec_log.txt 2>&1` でリダイレクトしている。

---

## ログ出力フォーマット（現行）

```
[toyamacityfm] elapsed=0s  ws_window=9s  recv=0KB  skip=0pg
[toyamacityfm] elapsed=9s  ws_window=9s  recv=120KB  skip=7pg
[toyamacityfm] elapsed=18s  ws_window=9s  recv=240KB  skip=14pg
```

- `skip=Npg`: OGGStitcher が除去した重複ページ数（累計）。1接続あたり約7ページ（=2.1秒分）増加するのが正常。

---

## 未解決・今後の課題

- 出力OGGファイルは複数の論理ビットストリームを連結したチェインOGG形式。VLC・mpvは正常再生するが、一部プレーヤーは先頭ストリームのみ再生する場合がある
- MP3変換はffmpeg経由で可能だが、依存追加のため見送り
- タスクスケジューラのタイムアウト設定は未調査（デフォルト72時間のはず）
