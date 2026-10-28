"""Synthetic wire data generation and model training for the LINKU payload.

Two datasets for two models, both described in `synthetic/README.md`:

    mask   photograph plus ground-truth mask, for the per-pixel segmenter
    path   mask plus ground-truth ordered path plus harvested branch
           decisions, for the branch scorer that does not exist yet

Generation is driven by `python -m synthetic.generate`.
"""
import sys

# The processing modules print arrows, check marks and box-drawing characters
# in their progress messages. On Windows the console is cp1252, so any of
# those raises UnicodeEncodeError, and because the print sits inside the
# operation it kills the operation rather than just the message. The
# auto-scale branch of SmartWireTracker does exactly this on any thick cable,
# which silently cost 15 of the first 24 harvested samples.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
