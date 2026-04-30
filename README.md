# JCBA 3局自動録音 - セットアップガイド

## 免責事項

本プログラムは個人の趣味で作成されたものであり、JCBAや関連団体とは一切関係ありません。テストなども十分でなく、実際の動作についても保証はできませんので、使用にあたっては自己責任でお願いします。

## 目的

このドキュメントは、JCBAの3局（富山シティエフエム、ラジオたかおか、FMとなみ）を自動で録音するためのセットアップ手順を説明します。PythonスクリプトとWindowsタスクスケジューラを使用して、指定した日時に自動的に録音が開始されるように構成します。

## 前提条件
- Windows PC（Windows 10以降推奨）
- Python 3.x がインストールされていること
- インターネット接続が必要
- 録音時点で PC の電源が入っていること（スリープは可）

---


## ファイル一覧

| ファイル | 説明 |
|---|---|
| jcba_rec.py | 録音メインスクリプト（Python） |
| rec_toyamacityfm.bat | ToyamaCityFM  4/30 12:30-13:00 |
| rec_radiotakaoka.bat | RadioTakaoka  5/1  13:00-14:00 |
| rec_fmtonami.bat | FMTonami       5/2  12:00-12:30 |
| register_tasks.bat | タスクスケジューラ登録 |
| install_libs.bat | Pythonライブラリのインストール |

---

## STEP 0: Pythonのインストール（未インストールの場合）
https://www.python.org/downloads/
- インストール時に「Add Python to PATH」にチェックを入れること

## STEP 1: ファイルのダウンロード
https://github.com/NAKADANobuhiro/FMSimulRec の右側 Release の Source code から最新の ZIP ダイルをダウンロードし、展開してください。

## STEP 2: 全ファイルを C:\RadioRec\ にコピー
展開したファイルすべてを C:\RadioRec\ に配置すること

## STEP 3: ライブラリのインストール
install_libs.bat をダブルクリック

## STEP 4: タスクスケジューラへの登録
register_tasks.bat を右クリック → 「管理者として実行」

## STEP 5: 動作テスト（録音当日の前に推奨）
コマンドプロンプトを開き、以下を実行:

```
python C:\RadioRec\jcba_rec.py fmtonami 30 C:\RadioRec\test.ogg
```

30秒後に C:\RadioRec\test.ogg が存在し、再生できることを確認してください。
OGGファイル（Opusコーデック）はVLCで再生できます。

正常動作時のログ例:
```
[fmtonami] Start recording 30s -> C:\RadioRec\test.ogg
[fmtonami] elapsed=0s  ws_window=9s  recv=0KB  skip=0pg
[fmtonami] elapsed=9s  ws_window=9s  recv=120KB  skip=7pg
[fmtonami] elapsed=18s  ws_window=9s  recv=240KB  skip=14pg
[fmtonami] Done. Total recv=360KB  Pages written=XXX  skipped=21  File=C:\RadioRec\test.ogg
```

`ws_window=9s` および接続ごとに `skip` が約7増加していれば正常です。

---

## 注意事項
- PC は電源を入れたままにしてください（シャットダウン不可）。スリープは問題ありません。
- 出力形式はOGG（Opusコーデック）です。VLC Player（無料）で再生できます。
- 録音の開始・終了・詳細ログは C:\RadioRec\rec_log.txt に記録されます。
- ネットワークが一時的に切断された場合でも自動リトライして録音を継続します。
- 再接続時のギャップはOGGStitcherが自動的に解消します（burst=2 のオーバーラップを利用）。

## 使用後のタスク削除

```
SCHTASKS /DELETE /TN "RadioRec_ToyamaCityFM_0430" /F
SCHTASKS /DELETE /TN "RadioRec_Takaoka_0501" /F
SCHTASKS /DELETE /TN "RadioRec_FMTonami_0502" /F
```

## リンク

https://github.com/NAKADANobuhiro/FMSimulRec
