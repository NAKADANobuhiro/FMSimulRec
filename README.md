# JCBA 3局自動録音 - セットアップガイド

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

## STEP 1: Pythonのインストール（未インストールの場合）
https://www.python.org/downloads/
- インストール時に「Add Python to PATH」にチェックを入れること

## STEP 2: 全ファイルを C:\RadioRec\ にコピー
6ファイルすべてを C:\RadioRec\ に配置すること

## STEP 3: ライブラリのインストール
install_libs.bat をダブルクリック

## STEP 4: タスクスケジューラへの登録
register_tasks.bat を右クリック → 「管理者として実行」

## STEP 5: 動作テスト（録音当日の前に推奨）
コマンドプロンプトを開き、以下を実行:
  python C:\RadioRec\jcba_rec.py fmtonami 30 C:\RadioRec\test.ogg

30秒後に C:\RadioRec\test.ogg が存在し、再生できることを確認してください。
OGGファイル（Opusコーデック）はVLCで再生できます。

---

## 注意事項
- PC は電源を入れたままにしてください（シャットダウン不可）。スリープは問題ありません。
- 出力形式はOGG（Opusコーデック）です。VLC Player（無料）で再生できます。
- 録音の開始・終了時刻は C:\RadioRec\rec_log.txt に記録されます。
- トークン有効期限は約15秒。初回接続のみ burst=5（5秒バッファ）、再接続時は burst=0（音声重複防止）。

## 使用後のタスク削除
  SCHTASKS /DELETE /TN "RadioRec_ToyamaCityFM_0430" /F
  SCHTASKS /DELETE /TN "RadioRec_Takaoka_0501" /F
  SCHTASKS /DELETE /TN "RadioRec_FMTonami_0502" /F
