# VAD Voice Recorder

`vad_recorder.py` is a simple voice-activity-detection (VAD) powered recorder that captures speech segments from your microphone, trims silence and saves each segment as an MP3 file.

## Features
- Uses WebRTC VAD to detect speech in real time.
- Automatically includes a short pre-roll and post-roll around detected speech.
- Saves each detected segment as an MP3 file using `ffmpeg` and `libmp3lame`.
- Supports custom output directories via the command line.

## Requirements
- Python 3.9+
- `ffmpeg` available on your `PATH`
- Python packages listed in `requirements.txt` (`pyaudio`, `webrtcvad`)

Install dependencies:


```bash
pip install -r requirements.txt
```

On macOS you may also need the PortAudio headers before installing `pyaudio`:


```bash
brew install portaudio
```

## Usage

Run the recorder from inside the `VADVoiceRecorder` directory (activate your virtual environment first if you created one):


```bash
python vad_recorder.py [--output-dir /path/to/save]
```

Press `Ctrl+C` to stop the recorder. Each captured segment is saved as an MP3 in the specified directory (default is `recordings`).

## Configuration

Key parameters can be adjusted by editing the constants near the top of `vad_recorder.py`:
- `SAMPLE_RATE`, `FRAME_MS`, `CHANNELS` control audio capture format.
- `VAD_MODE` sets the aggressiveness of speech detection (0–3).
- `PRE_ROLL_S` and `POST_ROLL_S` define how much audio is included before and after speech.
- `START_K` / `START_N` configure how many voiced frames are required to start recording.
- `MIN_SEG_S` / `MAX_SEG_S` define minimum and maximum segment lengths.

## Known Limitations
- Requires a functioning microphone accessible via PortAudio.
- Segments are saved sequentially without metadata beyond timestamps.
- Runs on a single input device; multi-device selection is not yet supported.

