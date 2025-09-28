import argparse, collections, datetime, os, subprocess
import pyaudio, webrtcvad

# ====== Configuration ======
SAMPLE_RATE = 16000          # WebRTC VAD supports: 8000/16000/32000/48000 Hz
FRAME_MS    = 30             # Frame duration: 10/20/30 ms only
CHANNELS    = 1              # Mono audio
SAMPLE_WIDTH= 2              # 16-bit PCM
VAD_MODE    = 2              # Aggressiveness: 0 (least) to 3 (most)
PRE_ROLL_S  = 2.0            # Seconds to include before speech detection
POST_ROLL_S = 2.0            # Seconds to include after speech ends
START_K     = 20             # Start recording if K out of N recent frames have speech
START_N     = 30             # Number of recent frames to check for speech
MIN_SEG_S   = 1.0            # Minimum recording duration in seconds
MAX_SEG_S   = 300            # Maximum recording duration in seconds
OUT_DIR     = "recordings"   # Output directory for recordings
MP3_BITRATE = "128k"         # MP3 encoding bitrate

# ====== Calculated Constants ======
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH
PRE_FRAMES  = int(PRE_ROLL_S * 1000 / FRAME_MS)
HANG_FRAMES = int(POST_ROLL_S * 1000 / FRAME_MS)
MIN_FRAMES  = int(MIN_SEG_S * 1000 / FRAME_MS)
MAX_FRAMES  = int(MAX_SEG_S * 1000 / FRAME_MS)

def parse_args():
    parser = argparse.ArgumentParser(description="Voice activity detection recorder")
    parser.add_argument("-o", "--output-dir", default=OUT_DIR,
                        help="Directory to save recordings (default: %(default)s)")
    return parser.parse_args()


def get_filepath(timestamp):
    """Generate a filepath from timestamp in YYYYMMDDHHMMSS format"""
    ts = timestamp.strftime("%Y%m%d%H%M%S")
    path = os.path.join(OUT_DIR, f"{ts}.mp3")
    return path
    
def save_as_mp3(path, raw_pcm: bytes):
    """Convert raw PCM data to MP3 using ffmpeg and save to file"""
    cmd = ["ffmpeg", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
           "-i", "pipe:0", "-acodec", "libmp3lame", "-b:a", MP3_BITRATE, "-y", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.stdin.write(raw_pcm)
        proc.stdin.close()
        proc.wait()
    except BrokenPipeError:
        pass

def reset_state():
    """Initialize or reset the recording state"""
    return {
        'collecting': False,  # Whether currently recording
        'seg_frames': [],     # Audio frames for current segment
        'silence_run': 0,     # Consecutive silent frames counter
        'seg_start_ts': None, # Timestamp when recording started
        'prebuffer': collections.deque(maxlen=PRE_FRAMES),  # Pre-roll buffer
        'recent_flags': collections.deque(maxlen=START_N)   # Recent voice activity flags
    }

def initialize_audio_stream():
    """Initialize PyAudio stream for audio input"""
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(SAMPLE_WIDTH),
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=FRAME_SAMPLES)
    return p, stream

def start_recording(state):
    """Initialize recording with pre-roll buffer"""
    state['collecting'] = True
    state['seg_frames'] = list(state['prebuffer'])
    state['silence_run'] = 0
    state['seg_start_ts'] = datetime.datetime.now(datetime.UTC)
    print("Recording started.")

def should_stop_recording(state):
    """Check if recording should stop based on silence or max duration"""
    return state['silence_run'] >= HANG_FRAMES or len(state['seg_frames']) >= MAX_FRAMES

def save_recording(state):
    """Save the recorded audio if it meets minimum duration"""
    if len(state['seg_frames']) >= MIN_FRAMES:
        outpath = get_filepath(state['seg_start_ts'])
        save_as_mp3(outpath, b"".join(state['seg_frames']))
        print("Recording stopped. Saved:", outpath)

def process_audio_frame(data, vad, state):
    """Process a single audio frame and update recording state"""
    # Check if frame contains speech
    is_voiced = vad.is_speech(data, SAMPLE_RATE)
    state['recent_flags'].append(1 if is_voiced else 0)
    
    if not state['collecting']:
        # Not recording: maintain pre-roll buffer and check for speech start
        state['prebuffer'].append(data)
        if sum(state['recent_flags']) >= START_K:
            start_recording(state)
    else:
        # Recording: accumulate frames and track silence
        state['seg_frames'].append(data)
        state['silence_run'] = 0 if is_voiced else state['silence_run'] + 1
        
        # Check if recording should stop
        if should_stop_recording(state):
            save_recording(state)
            return True  # Signal to reset state
    return False  # Continue with current state

def main():
    args = parse_args()

    global OUT_DIR
    OUT_DIR = os.path.abspath(os.path.expanduser(args.output_dir))

    os.makedirs(OUT_DIR, exist_ok=True)
    
    # Initialize audio stream and VAD
    p, stream = initialize_audio_stream()
    vad = webrtcvad.Vad(VAD_MODE)
    state = reset_state()

    print("Listening… Ctrl+C to stop.")
    try:
        while True:
            # Read audio frame
            data = stream.read(FRAME_SAMPLES, exception_on_overflow=False)
            if len(data) != FRAME_BYTES:
                continue
            
            # Process the audio frame
            if process_audio_frame(data, vad, state):
                state = reset_state()
                    
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

if __name__ == "__main__":
    main()