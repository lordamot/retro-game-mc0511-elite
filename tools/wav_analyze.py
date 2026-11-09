#!/usr/bin/env python3
"""wav_analyze.py - inspect a beeper WAV captured by uknc-headless.

Splits the capture into 20 ms windows, measures RMS activity and the
dominant frequency (by zero crossings) of each active window, and
prints a summary.  Used to verify that music/SFX actually play and
that the PPU tone loop calibration in tools/music_gen.py holds.

Usage:
    python3 tools/wav_analyze.py FILE.wav [--expect-tones]
        [--expect-freq HZ [--tolerance 0.05]]

--expect-tones  exit 1 unless at least 20% of windows carry a tone
--expect-freq   exit 1 unless the median active frequency is within
                --tolerance (relative) of HZ
"""

import argparse
import statistics
import struct
import sys
import wave


def read_wav(path):
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            sys.exit("error: expected mono 16-bit WAV")
        rate = w.getframerate()
        data = w.readframes(w.getnframes())
    n = len(data) // 2
    return rate, struct.unpack(f"<{n}h", data)


def window_stats(samples, rate, win_sec=0.02):
    win = max(1, int(rate * win_sec))
    out = []
    for i in range(0, len(samples) - win + 1, win):
        chunk = samples[i:i + win]
        mean = sum(chunk) / len(chunk)
        rms = (sum((s - mean) ** 2 for s in chunk) / len(chunk)) ** 0.5
        out.append((i / rate, rms))
    return out


def dominant_freq(samples, rate):
    """Dominant square-wave frequency from the modal sign-run length."""
    from collections import Counter
    runs = Counter()
    cur = samples[0] > 0
    n = 0
    for v in samples:
        b = v > 0
        if b == cur:
            n += 1
        else:
            runs[n] += 1
            cur, n = b, 1
    # ignore very long runs (silence between bursts) and 1-sample noise
    tone = {l: c for l, c in runs.items() if 2 <= l <= rate // 40}
    if not tone:
        return None
    # weight by time spent, then take the modal length
    mode = max(tone.items(), key=lambda kv: kv[0] * kv[1])[0]
    return rate / (2.0 * mode)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav")
    ap.add_argument("--expect-tones", action="store_true")
    ap.add_argument("--expect-freq", type=float)
    ap.add_argument("--tolerance", type=float, default=0.05)
    ap.add_argument("--active-rms", type=float, default=1000,
                    help="RMS above which a window counts as active "
                         "(default 1000; enveloped tunes need ~400)")
    ap.add_argument("--min-active", type=float, default=20,
                    help="--expect-tones: %% of active windows required")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    rate, samples = read_wav(args.wav)
    stats = window_stats(samples, rate)
    active = [(t, rms) for t, rms in stats if rms > args.active_rms]
    print(f"{args.wav}: {len(samples)/rate:.2f} s, "
          f"{len(active)}/{len(stats)} active 20 ms windows")
    if args.verbose:
        for t, rms in stats:
            mark = "*" if rms > args.active_rms else " "
            print(f"  {t:7.2f}s {mark} rms={rms:7.0f}")
    dom = dominant_freq(samples, rate)
    if dom:
        print(f"dominant frequency: {dom:.1f} Hz")
    if args.expect_tones:
        need = max(1, int(len(stats) * args.min_active / 100))
        if len(active) < need:
            sys.exit(f"FAIL: fewer than {args.min_active:g}% of windows "
                     "carry sound")
        print("OK: tones present")
    if args.expect_freq is not None:
        if dom is None:
            sys.exit("FAIL: no tone found")
        rel = abs(dom - args.expect_freq) / args.expect_freq
        if rel > args.tolerance:
            sys.exit(f"FAIL: dominant {dom:.1f} Hz differs from expected "
                     f"{args.expect_freq:.1f} Hz by {rel*100:.1f}%")
        print(f"OK: frequency within {args.tolerance*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
