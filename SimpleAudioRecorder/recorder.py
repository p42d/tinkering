#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mac用・常時録音スクリプト（シンプル実装）
- WAV 保存（常時）
- --mp3 指定でセグメント毎に ffmpeg で MP3 も作成（WAV はデフォルト削除）
- セグメント未指定: 1ファイルに連続保存
- セグメント指定: n秒ごとにファイル分割
- ファイル名: 録音開始日時 yyyyMMddHHmmss.wav / .mp3
"""

import argparse
import datetime as dt
import os
import queue
import signal
import subprocess
import sys
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

STOP_FLAG = False

def fmt_now_for_filename(t: dt.datetime) -> str:
    return t.strftime("%Y%m%d%H%M%S")

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def encode_mp3_with_ffmpeg(wav_path: str, mp3_path: str, keep_wav: bool = False, vbr_quality: int = 2):
    """
    ffmpeg -i input.wav -codec:a libmp3lame -q:a 2 output.mp3
    """
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", str(vbr_quality), mp3_path],
            check=True
        )
        if not keep_wav:
            os.remove(wav_path)
    except FileNotFoundError:
        print("[WARN] ffmpeg が見つかりません。brew install ffmpeg してください。", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"[WARN] ffmpeg 変換に失敗: {e}", file=sys.stderr)

class RotatingWavWriter:
    """
    入力ストリームから受け取った音声フレームを、セグメント長ごとにWAVファイルへローテーション保存。
    セグメント未指定（None または 0）の場合は 1ファイル連続保存。
    """
    def __init__(self, outdir: str, samplerate: int, channels: int,
                 segment_sec: int | None, do_mp3: bool, keep_wav: bool, vbr_quality: int):
        self.outdir = outdir
        self.samplerate = samplerate
        self.channels = channels
        self.segment_sec = None if not segment_sec or segment_sec <= 0 else int(segment_sec)
        self.do_mp3 = do_mp3
        self.keep_wav = keep_wav
        self.vbr_quality = vbr_quality

        self.current_file = None  # type: sf.SoundFile | None
        self.current_start = None  # type: dt.datetime | None
        self.samples_written_this_segment = 0
        self.segment_samples = (self.segment_sec * self.samplerate) if self.segment_sec else None

        # エンコード用のジョブキュー（WAV→MP3を非同期化して取りこぼしを防止）
        self.encode_q: queue.Queue[tuple[str, str]] = queue.Queue()
        self.enc_thread = threading.Thread(target=self._encode_worker, daemon=True)
        self.enc_thread.start()

    def _open_new_file(self):
        if self.current_file is not None:
            self._close_current_file()

        self.current_start = dt.datetime.now()
        fname = fmt_now_for_filename(self.current_start) + ".wav"
        fpath = os.path.join(self.outdir, fname)
        self.current_file = sf.SoundFile(fpath, mode="w", samplerate=self.samplerate,
                                         channels=self.channels, subtype="PCM_16")
        self.samples_written_this_segment = 0
        # print(f"[INFO] 開始: {fpath}")

    def _close_current_file(self):
        if self.current_file is None:
            return

        wav_path = self.current_file.name
        self.current_file.flush()
        self.current_file.close()

        if self.do_mp3:
            mp3_path = os.path.splitext(wav_path)[0] + ".mp3"
            # 非同期エンコード
            self.encode_q.put((wav_path, mp3_path))

        self.current_file = None

    def _encode_worker(self):
        while True:
            try:
                wav_path, mp3_path = self.encode_q.get()
                # すでにSTOP_FLAGでも、キューに残った分は処理して良い
                encode_mp3_with_ffmpeg(wav_path, mp3_path, keep_wav=self.keep_wav, vbr_quality=self.vbr_quality)
            except Exception as e:
                print(f"[WARN] エンコードスレッドで例外: {e}", file=sys.stderr)
            finally:
                self.encode_q.task_done()

    def write(self, frames: np.ndarray):
        if self.current_file is None:
            self._open_new_file()

        self.current_file.write(frames)
        self.samples_written_this_segment += len(frames)

        if self.segment_samples and self.samples_written_this_segment >= self.segment_samples:
            # セグメント切り替え
            self._open_new_file()

    def close(self):
        self._close_current_file()
        # エンコード完了待ち（必要に応じて）
        self.encode_q.join()

def signal_handler(sig, frame):
    global STOP_FLAG
    STOP_FLAG = True
    print("\n[INFO] 終了処理中...（Ctrl+C）")

def main():
    parser = argparse.ArgumentParser(description="Mac用 常時録音スクリプト（WAV/MP3, セグメント可）")
    parser.add_argument("--outdir", "-o", type=str, default="./recordings", help="保存ディレクトリ（既定: ./recordings）")
    parser.add_argument("--samplerate", "-r", type=int, default=48000, help="サンプルレート（既定: 48000）")
    parser.add_argument("--channels", "-c", type=int, default=1, help="チャンネル数（1=モノラル, 2=ステレオ。既定: 1）")
    parser.add_argument("--segment", "-s", type=int, default=0, help="ファイル分割の間隔（秒）。0 または未指定で1ファイル")
    parser.add_argument("--mp3", action="store_true", help="各セグメントを ffmpeg で MP3 へ変換（WAVは既定で削除）")
    parser.add_argument("--keep-wav", action="store_true", help="--mp3 指定時も WAV を残す")
    parser.add_argument("--device", type=str, default=None, help="録音デバイス名/番号（未指定で既定デバイス）")
    parser.add_argument("--blocksize", type=int, default=2048, help="1回に処理するフレーム数（既定: 2048）")
    parser.add_argument("--latency", type=str, default="low", help="低遅延プロファイル: 'low' 推奨")
    parser.add_argument("--vbrq", type=int, default=2, help="MP3 VBR 品質（0=最高〜9=低, 既定:2）")
    args = parser.parse_args()

    ensure_dir(args.outdir)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    writer = RotatingWavWriter(
        outdir=args.outdir,
        samplerate=args.samplerate,
        channels=args.channels,
        segment_sec=args.segment,
        do_mp3=args.mp3,
        keep_wav=args.keep_wav,
        vbr_quality=args.vbrq,
    )

    q_frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)

    def audio_callback(indata, frames, time, status):
        if status:
            # xruns など
            print(f"[WARN] {status}", file=sys.stderr)
        # float32(-1..1) を 16bit に揃える必要は soundfile 側で subtype 指定済みなので不要
        try:
            q_frames.put_nowait(indata.copy())
        except queue.Full:
            # 取りこぼし防止。最小限のログ。
            pass

    stream = sd.InputStream(
        device=args.device,
        channels=args.channels,
        samplerate=args.samplerate,
        blocksize=args.blocksize,
        latency=args.latency,
        dtype="float32",
        callback=audio_callback,
    )

    print("[INFO] 録音開始。終了するには Ctrl+C")
    try:
        with stream:
            while not STOP_FLAG:
                try:
                    frames = q_frames.get(timeout=0.5)
                    writer.write(frames)
                except queue.Empty:
                    continue
    finally:
        writer.close()
        print("[INFO] 正常終了")

if __name__ == "__main__":
    main()