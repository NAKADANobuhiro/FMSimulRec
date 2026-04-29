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
- `burst`: 初回接続=5（秒バッファ）、再接続=0（音声重複防止）
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
| 音声がループする | 再接続のたびに `burst=5` → 過去5秒分が重複 | 再接続時は `burst=0` に変更 |
| 20分で録音が途切れる | `fetch_token` 例外でスクリプト終了 | try/except + 5秒待ちリトライを追加 |

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
TOKEN_MARGIN  = 5    # トークン期限切れN秒前に再取得（実効接続時間 ≈ 10秒）
CONNECT_TIMEOUT = 10 # WebSocket接続タイムアウト（秒）
FETCH_RETRY_WAIT = 5 # トークン取得失敗時のリトライ待機（秒）
```

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

## 未解決・今後の課題

- OGGのシーケンス番号が再接続のたびにリセットされる（プレーヤーによっては誤認識の可能性）
- MP3変換はffmpeg経由で可能だが、依存追加のため見送り
- タスクスケジューラのタイムアウト設定は未調査（デフォルト72時間のはず）
