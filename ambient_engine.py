"""
ambient_engine.py

Live-Engine für den Dauerbetrieb (48h): spielt das gewobene Ambient endlos
(nie exakt wiederholend, da laufend neu generiert) über die Soundkarte /
SolidDrive-Transducer ab und lässt sich von deiner Mic-Input-Erkennung aus
ansteuern: engine.trigger_sharp_inhale() duckt das Ambient kurz und mischt
den Sharp-Inhale-Clip ein.

Einbindung in app_dual_claude.py (sinngemäss):

    from ambient_engine import AmbientEngine

    engine = AmbientEngine(
        clip_a_path="human_breathing__int__4-....wav",
        clip_b_path="slow_human_breathing__3-....wav",
        sharp_inhale_path="human_sharp_inhalati__2-....wav",
        device="SolidDrive",          # sounddevice-Gerätename oder Index,
                                       # None = System-Default
    )
    engine.start()

    # ... in deiner bestehenden Audio-Input-Callback / Trigger-Logik:
    def on_audio_input_detected():
        engine.trigger_sharp_inhale()
        # ... restliche Logik (Claude-Aufruf, Drucker etc.)

    # beim Beenden:
    engine.stop()

Benötigt: pip install sounddevice soundfile numpy
"""

import threading
import queue
import time
import numpy as np

from ambient_weave import load_wav, seamless_extend, complementary_envelopes


def resolve_output_device(name_or_index):
    """Findet ein Ausgabegerät robust — per Index ODER per (Teil-)Name.

    Namen sind stabiler als Indizes: wenn Geräte in unterschiedlicher
    Reihenfolge an-/abgesteckt werden, verschieben sich Indizes, aber der
    Name (z.B. 'Externe Kopfhörer', oder später der Name des Audio-Interfaces
    am Installationsort) bleibt gleich.

    name_or_index: int (Index) ODER str (Teil des Gerätenamens, z.B. 'Kopfhörer').
    None -> Systemstandard.
    """
    import sounddevice as sd

    if name_or_index is None or isinstance(name_or_index, int):
        return name_or_index

    devices = sd.query_devices()
    matches = [
        (i, d) for i, d in enumerate(devices)
        if name_or_index.lower() in d["name"].lower() and d["max_output_channels"] >= 2
    ]
    if not matches:
        available = "\n".join(
            f"  {i}: {d['name']} ({d['max_output_channels']} out)"
            for i, d in enumerate(devices)
        )
        raise RuntimeError(
            f"Kein Ausgabegerät gefunden, das '{name_or_index}' enthält "
            f"und mind. 2 Kanäle hat.\nVerfügbare Geräte:\n{available}"
        )
    idx, dev = matches[0]
    print(f"♪ Ambient-Ausgabe: '{dev['name']}' (Index {idx})")
    return idx


class AmbientEngine:
    def __init__(self, clip_a_path, clip_b_path, sharp_inhale_path,
                 sr=48000, block_seconds=20, crossfade_s=2.0,
                 env_floor=0.30, env_period_range_s=(18, 45),
                 duck_db=-14.0, duck_attack_ms=150, duck_release_ms=1200,
                 device=None, blocksize=1024, inhale_gain=0.45):
        self.sr = sr
        self.block_seconds = block_seconds
        self.crossfade_s = crossfade_s
        self.env_floor = env_floor
        self.env_period_range_s = env_period_range_s
        self.device = device
        self.blocksize = blocksize

        self.clip_a = load_wav(clip_a_path, sr)
        self.clip_b = load_wav(clip_b_path, sr)
        self.sharp = load_wav(sharp_inhale_path, sr) * inhale_gain
        self.channels = self.clip_a.shape[1]

        self._q = queue.Queue(maxsize=4)
        self._stop_flag = threading.Event()
        self._producer_thread = None
        self._stream = None

        # Playback-Zustand (nur im Audio-Callback-Thread verändert)
        self._current_block = np.zeros((0, self.channels), dtype=np.float32)
        self._pos = 0
        self._prev_tail = None  # für nahtlosen Übergang zwischen Blöcken

        # Ducking / Sharp-Inhale-Zustand
        self._duck_gain = 1.0
        self._duck_target = 1.0
        self._duck_db = duck_db
        self._duck_attack_n = int(duck_attack_ms / 1000 * sr)
        self._duck_release_n = int(duck_release_ms / 1000 * sr)
        self._pending_inhale = None  # (array, position) wenn gerade getriggert
        self._trigger_lock = threading.Lock()
        self._trigger_flag = threading.Event()

    # -- Hintergrund-Produzent: erzeugt laufend neue, frische Ambient-Blöcke --
    def _producer(self):
        rng = np.random.default_rng()
        while not self._stop_flag.is_set():
            n = int(self.block_seconds * self.sr)
            ext_a = seamless_extend(self.clip_a, n, self.sr, rng=rng)
            ext_b = seamless_extend(self.clip_b, n, self.sr, rng=rng)
            env_a, env_b = complementary_envelopes(
                n, self.sr, self.env_floor, self.env_period_range_s, rng)
            block = ext_a * env_a + ext_b * env_b
            peak = np.max(np.abs(block))
            if peak > 0:
                block = block * (0.7 / peak)  # ~ -3 dBFS Ziel-Peak
            try:
                self._q.put(block.astype(np.float32), timeout=5)
            except queue.Full:
                pass

    def _next_block_with_crossfade(self):
        block = self._q.get()
        cf_n = int(self.crossfade_s * self.sr)
        if self._prev_tail is not None:
            head = block[:cf_n]
            t = np.linspace(0, np.pi / 2, cf_n)[:, None]
            blended = self._prev_tail * np.cos(t) + head * np.sin(t)
            block = np.concatenate([blended, block[cf_n:]], axis=0)
        self._prev_tail = block[-cf_n:]
        return block[:-cf_n]  # Rest der Überblendung geht in nächsten Block

    # -- Öffentliche API --
    def trigger_sharp_inhale(self):
        """Von deiner Mic-Input-Logik aufrufen. Duckt das Ambient kurz und
        mischt den Sharp-Inhale-Clip einmalig ein."""
        with self._trigger_lock:
            self._pending_inhale = (self.sharp.copy(), 0)
        self._trigger_flag.set()

    def start(self):
        import sounddevice as sd
        self._producer_thread = threading.Thread(target=self._producer, daemon=True)
        self._producer_thread.start()

        def callback(outdata, frames, time_info, status):
            if status:
                pass  # bei Bedarf Xruns loggen

            out = np.zeros((frames, self.channels), dtype=np.float32)
            filled = 0
            while filled < frames:
                if self._pos >= len(self._current_block):
                    self._current_block = self._next_block_with_crossfade()
                    self._pos = 0
                take = min(frames - filled, len(self._current_block) - self._pos)
                out[filled:filled + take] = self._current_block[self._pos:self._pos + take]
                self._pos += take
                filled += take

            # Ducking + Sharp-Inhale-Overlay
            if self._trigger_flag.is_set():
                self._trigger_flag.clear()
                self._duck_target = 10 ** (self._duck_db / 20)

            gain = np.full(frames, self._duck_gain, dtype=np.float32)
            step_attack = 1.0 / max(self._duck_attack_n, 1)
            step_release = 1.0 / max(self._duck_release_n, 1)
            for i in range(frames):
                if self._duck_gain > self._duck_target:
                    self._duck_gain = max(self._duck_target, self._duck_gain - step_attack)
                elif self._duck_gain < 1.0 and self._pending_inhale is None:
                    self._duck_gain = min(1.0, self._duck_gain + step_release)
                gain[i] = self._duck_gain
            out *= gain[:, None]

            if self._pending_inhale is not None:
                clip, ppos = self._pending_inhale
                take = min(frames, len(clip) - ppos)
                if take > 0:
                    out[:take] += clip[ppos:ppos + take]
                    ppos += take
                if ppos >= len(clip):
                    self._pending_inhale = None
                    self._duck_target = 1.0
                else:
                    self._pending_inhale = (clip, ppos)

            np.clip(out, -1.0, 1.0, out=out)
            outdata[:] = out

        resolved_device = resolve_output_device(self.device)
        self._stream = sd.OutputStream(
            samplerate=self.sr, channels=self.channels, device=resolved_device,
            blocksize=self.blocksize, callback=callback)
        self._stream.start()

    def stop(self):
        self._stop_flag.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
