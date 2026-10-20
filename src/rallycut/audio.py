"""Band-limited spectral-flux onset baseline; an onset is not a certified hit."""

from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import find_peaks, stft

from .media import executable


def detect_onsets(meta, threads=2):
    if meta["audio_stream_index"] is None:
        return [], {"available": False, "reason": "no audio stream"}
    sr, hop = 16000, 160
    # Disk-backed PCM keeps memory bounded for hour-long recordings.
    with tempfile.TemporaryDirectory(prefix="rallycut-audio-") as directory:
        pcm = Path(directory) / "audio.f32"
        subprocess.run(
            [executable("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", str(threads),
             "-i", meta["path"], "-map", f"0:{meta['audio_stream_index']}", "-vn", "-ac", "1",
             "-ar", str(sr), "-f", "f32le", str(pcm)],
            capture_output=True, check=True,
        )
        if pcm.stat().st_size < 512 * 4:
            return [], {"available": True, "reason": "audio too short"}
        samples = np.memmap(pcm, dtype="<f4", mode="r")
        onsets = []
        peak_strengths = []
        try:
            for start in range(0, len(samples), sr * 30):
                # Overlap both sides; retain only peaks in the central chunk.
                left, right = max(0, start - sr), min(len(samples), start + sr * 31)
                if right - left < 512:
                    continue
                f, t, z = stft(np.asarray(samples[left:right]), sr, nperseg=512,
                              noverlap=512-hop, boundary=None, padded=False)
                power = np.abs(z[(f >= 900) & (f <= 5000)])
                flux = np.maximum(0, np.diff(np.log1p(100 * power), axis=1, prepend=0)).mean(axis=0)
                local = median_filter(flux, size=101, mode="nearest")
                residual = np.maximum(0, flux - local)
                mad = np.median(np.abs(residual - np.median(residual)))
                threshold = max(float(np.percentile(residual, 88)), float(5 * mad), 0.001)
                peaks, _ = find_peaks(residual, height=threshold, prominence=threshold * .5,
                                      distance=round(.30 * sr / hop))
                for p in peaks:
                    absolute = float(left / sr + t[p])
                    stamp = absolute + meta["audio_offset_seconds"]
                    if (start / sr <= absolute < (start + sr * 30) / sr
                            and 0 <= stamp < meta["duration_seconds"]):
                        onsets.append(round(stamp, 4))
                        peak_strengths.append(float(residual[p]))
        finally:
            samples._mmap.close()
    # Chunk-edge peaks may be closer than the within-chunk refractory period.
    retained = []
    for stamp, strength in zip(onsets, peak_strengths):
        if retained and stamp - retained[-1][0] < .30:
            if strength > retained[-1][1]:
                retained[-1] = (stamp, strength)
        else:
            retained.append((stamp, strength))
    return [t for t, _ in retained], {"available": True, "onset_count": len(retained),
                                    "sample_rate": sr, "certified_racket_hits": False}
