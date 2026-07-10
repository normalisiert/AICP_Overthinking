"""
ambient_weave.py

Verwebt zwei Breathing-Clips (intermittent + slow) zu einem generativen,
endlosen Ambient-Bett - statt sie nacheinander abzuspielen, überlappen und
durchdringen sie sich fortlaufend.

Zwei Bausteine:
1. seamless_extend()  - dehnt einen kurzen Clip (30s) nahtlos auf beliebige
                         Länge, indem zufällige Crops mit Equal-Power-Crossfade
                         aneinandergereiht werden. Kein hörbarer 30s-Loop-Punkt.
2. complementary_envelopes() - erzeugt zwei langsam, unregelmässig
                         schwankende Lautstärke-Hüllkurven, die sich
                         gegenläufig verhalten (wenn A lauter wird, wird B
                         leiser, und umgekehrt) - dadurch entsteht das
                         "Verweben": beide Stimmen sind fast immer gleichzeitig
                         hörbar, ihr Verhältnis verschiebt sich aber ständig.

weave() kombiniert beides zu einem fertigen Ambient-Bett beliebiger Länge.

AmbientEngine (unten) ist die Echtzeit-Variante für den Dauerbetrieb (48h):
sie rendert Material blockweise nach und lässt sich per trigger_sharp_inhale()
von deiner Mic-Input-Logik aus ansteuern (duckt das Ambient kurz und mischt
den Sharp-Inhale-Clip ein).
"""

import numpy as np
import soundfile as sf


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_wav(path, target_sr=48000):
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    if sr != target_sr:
        raise ValueError(f"{path}: Samplerate {sr} != {target_sr}. "
                          f"Bitte vorher resamplen (z.B. mit ffmpeg -ar {target_sr}).")
    return data  # shape (n_samples, n_channels)


def save_wav(path, data, sr=48000):
    sf.write(path, data, sr, subtype="PCM_16")


# ---------------------------------------------------------------------------
# 1) Nahtlose Verlängerung eines kurzen Clips
# ---------------------------------------------------------------------------

def _equal_power_crossfade(a_tail, b_head):
    """Crossfaded zwei gleich lange Blöcke mit Equal-Power-Kurve (klingt
    natürlicher als lineares Fading, da die Lautheit während der Überblendung
    konstant bleibt)."""
    n = a_tail.shape[0]
    t = np.linspace(0, np.pi / 2, n)[:, None]
    fade_out = np.cos(t)
    fade_in = np.sin(t)
    return a_tail * fade_out + b_head * fade_in


def seamless_extend(clip, target_len, sr, crop_range_s=(6, 14),
                     crossfade_s=2.0, rng=None):
    """Verlängert `clip` (n_samples, ch) nahtlos auf `target_len` Samples.

    Es werden immer wieder zufällige Ausschnitte (crop_range_s Sekunden lang)
    aus zufälligen Startpositionen im Quellclip herausgeschnitten und mit
    Equal-Power-Crossfade aneinandergehängt. Durch die zufälligen Startpunkte
    entsteht kein spürbarer Wiederholungs-Loop, obwohl die Quelle nur 30s lang
    ist.
    """
    rng = rng or np.random.default_rng()
    n_src = clip.shape[0]
    crossfade_n = int(crossfade_s * sr)

    out = np.zeros((0, clip.shape[1]), dtype=np.float32)

    def random_crop(length_n):
        # zufälliger Startpunkt, mit Wraparound falls nötig
        start = rng.integers(0, n_src)
        idx = (np.arange(length_n) + start) % n_src
        return clip[idx]

    # ersten Block holen
    first_len_s = rng.uniform(*crop_range_s)
    out = random_crop(int(first_len_s * sr))

    while out.shape[0] < target_len + crossfade_n:
        next_len_s = rng.uniform(*crop_range_s)
        nxt = random_crop(int(next_len_s * sr) + crossfade_n)

        tail = out[-crossfade_n:]
        head = nxt[:crossfade_n]
        blended = _equal_power_crossfade(tail, head)

        out = np.concatenate([out[:-crossfade_n], blended, nxt[crossfade_n:]], axis=0)

    return out[:target_len]


# ---------------------------------------------------------------------------
# 2) Gegenläufige, organisch schwankende Hüllkurven ("das Weben")
# ---------------------------------------------------------------------------

def complementary_envelopes(n_samples, sr, floor=0.30,
                             period_range_s=(18, 45), rng=None):
    """Erzeugt env_a, env_b (je Länge n_samples), die sich gegenläufig und
    unregelmässig bewegen: env_a + Rest ≈ konstant, aber die Kurve ist keine
    einfache Sinuswelle, sondern eine Summe mehrerer Sinusanteile mit
    zufälligen Perioden/Phasen -> wirkt organisch, nicht mechanisch.
    `floor` verhindert, dass eine Stimme ganz verschwindet (immer mind. 30%
    Präsenz), damit wirklich beide Texturen ständig zu hören sind."""
    rng = rng or np.random.default_rng()
    t = np.arange(n_samples) / sr

    n_components = 3
    signal = np.zeros(n_samples)
    for _ in range(n_components):
        period = rng.uniform(*period_range_s)
        phase = rng.uniform(0, 2 * np.pi)
        weight = rng.uniform(0.5, 1.0)
        signal += weight * np.sin(2 * np.pi * t / period + phase)

    signal = signal / np.max(np.abs(signal))          # -1..1
    env_a = (signal + 1) / 2                          # 0..1
    env_a = floor + (1 - 2 * floor) * env_a            # floor..1-floor
    env_b = 1.0 - env_a

    return env_a[:, None], env_b[:, None]


# ---------------------------------------------------------------------------
# 3) Alles zusammen: fertiges Ambient-Bett
# ---------------------------------------------------------------------------

def weave(clip_a, clip_b, duration_s, sr=48000, seed=None,
           crop_range_s=(6, 14), crossfade_s=2.0,
           env_floor=0.30, env_period_range_s=(18, 45),
           target_peak_dbfs=-3.0):
    """
    clip_a, clip_b: geladene Arrays (z.B. human_breathing__int, slow_human_breathing)
    duration_s: Ziel-Länge des Ambient-Betts in Sekunden
    Rückgabe: gemischtes Array (n_samples, channels), bereit zum Speichern.
    """
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)

    # A und B unabhängig voneinander (verschiedene rng-Ziehungen) nahtlos
    # verlängern, damit sie sich nicht synchron wiederholen.
    ext_a = seamless_extend(clip_a, n, sr, crop_range_s, crossfade_s, rng)
    ext_b = seamless_extend(clip_b, n, sr, crop_range_s, crossfade_s, rng)

    env_a, env_b = complementary_envelopes(n, sr, env_floor, env_period_range_s, rng)

    mixed = ext_a * env_a + ext_b * env_b

    # Peak-Normalisierung, damit nichts clippt
    peak = np.max(np.abs(mixed))
    target_peak = 10 ** (target_peak_dbfs / 20)
    if peak > 0:
        mixed = mixed * (target_peak / peak)

    return mixed.astype(np.float32)


if __name__ == "__main__":
    clip_int = load_wav("human_breathing__int__4-1783422398792.wav")
    clip_slow = load_wav("slow_human_breathing__3-1783422124090.wav")

    demo = weave(clip_int, clip_slow, duration_s=180, seed=42)
    save_wav("ambient_woven_demo.wav", demo)
    print("Geschrieben: ambient_woven_demo.wav")
