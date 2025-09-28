# Simple Audio Recorder

Mac 向けの常時録音スクリプト `recorder.py` では、マイク入力を WAV に保存し、必要に応じて ffmpeg で MP3 へ自動変換できます。

## 必要環境

- Python 3.11 以上
- 依存ライブラリ: `pip install -r requirements.txt`
- MP3 を作成する場合は ffmpeg (`brew install ffmpeg` など)

## 使い方

```bash
python recorder.py [options]
```

録音開始後は `Ctrl+C` で停止します。録音ファイルは開始時刻 (`yyyyMMddHHmmss`) を元に名付けられます。

### 主なオプション

- `--outdir / -o`: 保存先ディレクトリ (既定: `./recordings`)
- `--samplerate / -r`: サンプルレート (既定: `48000`)
- `--channels / -c`: チャンネル数、モノラルなら `1`、ステレオなら `2`
- `--segment / -s`: ファイル分割間隔（秒）。`0` または未指定で単一ファイル
- `--mp3`: 録音終了後に各セグメントを MP3 へ変換（WAV は既定で削除）
- `--keep-wav`: `--mp3` 指定時でも WAV を残す
- `--device`: 利用する入力デバイス番号または名前
- `--blocksize`: 1 回の処理フレーム数 (既定: `2048`)
- `--latency`: 低遅延プロファイル (既定: `low`)
- `--vbrq`: MP3 エンコード品質 (0=最高〜9=低、既定: `2`)

### サンプルコマンド

分割なしで WAV のみ保存:

```bash
python recorder.py --outdir ./recordings
```

10 秒ごとに MP3 を出力しつつ WAV も保持:

```bash
python recorder.py --segment 10 --mp3 --keep-wav
```

## 動作の仕組み

入力ストリームから受け取った音声は `queue.Queue` に蓄積され、バックグラウンドで WAV ファイルに書き込まれます。`--segment` を設定すると、指定時間ごとに新しいファイルへ切り替えます。また MP3 変換は別スレッドで非同期に行い、録音の取りこぼしを防ぎます。
