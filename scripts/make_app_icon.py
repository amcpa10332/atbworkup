"""
One-off: turn Blueprint Trial Balance Icon.png (flat white background, the
badge itself is an opaque rounded square) into a transparent-background PNG
and multi-resolution Windows (.ico) and macOS (.icns) icons, saved into
atbworkup/assets/.

Approach: flood-fill connectivity from the image border, not a global color
threshold -- the white "B"/"T"/"BLUEPRINT" lettering INSIDE the navy badge
is the same white as the background, but it's enclosed by navy and never
touches the border, so it survives untouched while the true background
(which is one contiguous region touching all four edges) gets cleared.

Run from the project root:
    python scripts/make_app_icon.py
"""
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter, label

SRC = Path("Blueprint Trial Balance Icon.png")
OUT_DIR = Path("atbworkup/assets")
OUT_PNG = OUT_DIR / "app_icon.png"
OUT_ICO = OUT_DIR / "app_icon.ico"
OUT_ICNS = OUT_DIR / "app_icon.icns"

# A pixel counts as "background-ish" if every channel is at least this
# bright -- catches pure white plus the soft drop-shadow's light-gray edge
# pixels, without reaching into the navy badge itself.
WHITE_THRESHOLD = 225


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    im = Image.open(SRC).convert("RGB")
    arr = np.asarray(im).astype(np.int16)

    whiteish = (arr.min(axis=2) >= WHITE_THRESHOLD)

    # Connected components of the "whiteish" mask; keep only the components
    # that touch the image border -- that's the real background. Any
    # whiteish blob fully enclosed inside the badge (letters, wordmark) is
    # left alone.
    labeled, n = label(whiteish)
    border_labels = set(labeled[0, :]) | set(labeled[-1, :]) | \
                    set(labeled[:, 0]) | set(labeled[:, -1])
    border_labels.discard(0)

    background_mask = np.isin(labeled, list(border_labels))

    # Grow the background mask out by a couple pixels so the faint
    # transitional shadow pixels right at the badge edge (too gray to hit
    # WHITE_THRESHOLD, but not really "icon" either) get cleared too,
    # instead of leaving a dull halo.
    background_mask = binary_dilation(background_mask, iterations=2)

    alpha = np.where(background_mask, 0, 255).astype(np.float32)
    # Feather the cut edge so it anti-aliases instead of looking jagged.
    alpha = gaussian_filter(alpha, sigma=1.2)
    alpha = np.clip(alpha, 0, 255).astype(np.uint8)

    rgba = np.dstack([np.asarray(im), alpha])
    out = Image.fromarray(rgba, mode="RGBA")
    out.save(OUT_PNG)
    print(f"Wrote {OUT_PNG} ({out.size[0]}x{out.size[1]}, background removed)")

    # Windows .ico wants a stack of square sizes; Pillow builds them all
    # from one source image when you pass `sizes`.
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                  (128, 128), (256, 256)]
    out.save(OUT_ICO, format="ICO", sizes=icon_sizes)
    print(f"Wrote {OUT_ICO} ({', '.join(f'{w}x{h}' for w, h in icon_sizes)})")

    # macOS .icns -- Pillow writes the Apple icon container format directly,
    # no macOS tooling (iconutil) required, so this works from any OS.
    icns_sizes = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256),
                  (512, 512), (1024, 1024)]
    out.save(OUT_ICNS, format="ICNS", sizes=icns_sizes)
    print(f"Wrote {OUT_ICNS} ({', '.join(f'{w}x{h}' for w, h in icns_sizes)})")


if __name__ == "__main__":
    main()
