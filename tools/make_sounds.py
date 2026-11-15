"""Erzeugt den Blasen-Sound (assets/sounds/bubble.wav) rein rechnerisch – keine fremden Audiodateien.

Aufruf:  py tools\\make_sounds.py
Klang: kurzer „Blub“ – Sinus, dessen Tonhöhe schnell steigt, mit weichem Anschlag und schnellem Ausklingen.
Dauer/Tonhöhen/Lautstärke stehen oben als Konstanten.
"""
import math
import struct
import wave
from pathlib import Path

RATE = 44100
DURATION = 0.13        # Sekunden
F_START, F_END = 330.0, 1150.0   # Tonhöhe (Hz) am Anfang/Ende
PEAK = 0.55            # 0..1
OUT = Path(__file__).resolve().parent.parent / "emu_launcher" / "assets" / "sounds" / "bubble.wav"


def build() -> bytes:
    n = int(RATE * DURATION)
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        t = i / RATE
        x = i / n
        freq = F_START * (F_END / F_START) ** (x ** 0.55)     # schnell steigend, am Ende flacher
        phase += 2 * math.pi * freq / RATE
        attack = min(1.0, t / 0.004)                           # 4 ms Anschlag gegen Knacken
        decay = math.exp(-t * 26)                              # Ausklingen
        tone = math.sin(phase) + 0.25 * math.sin(2 * phase)    # leichter Oberton = rundere „Blase“
        sample = PEAK * attack * decay * tone / 1.25
        frames += struct.pack("<h", int(max(-1, min(1, sample)) * 32767))
    return bytes(frames)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(build())
    print("geschrieben:", OUT, f"({OUT.stat().st_size} Bytes)")


if __name__ == "__main__":
    main()
