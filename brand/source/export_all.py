"""Regenerates the whole kit: masters, SVG variants, web icons and the presentation board.

Needs the logo-design skill (LOGO_SKILL = its folder) and a Chromium binary (CHROME) for the PNGs.
"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
SK = os.path.join(os.environ["LOGO_SKILL"], "scripts")
def run(*a): subprocess.run([sys.executable, *a], cwd=ROOT, check=True)
LIME, INK = "#C4F03A", "#151515"
run(os.path.join(HERE, "build.py"))
# Variants come from the plain masters (no tile): one-colour conversion would fill a tile solid.
run(os.path.join(SK, "export_variants.py"), "eco-symbol.svg", "--title", "Eco", "--mono", LIME, "--mono", INK,
    "--icon-bg", LIME, "--icon-fg", INK, "--favicon-source", "eco-symbol-small.svg", "--optical-offset", "-0.02",
    "--out-dir", "symbol")
for n in ("eco-horizontal", "eco-stacked"):
    run(os.path.join(SK, "export_variants.py"), f"lockups/{n}-on-dark.svg", "--name", n, "--title", "Eco",
        "--only", "black", "white", "mono", "--mono", LIME, "--out-dir", "lockups")
run(os.path.join(SK, "export_variants.py"), "eco-wordmark.svg", "--title", "Eco", "--only", "black", "white", "mono",
    "--mono", LIME, "--out-dir", "lockups")
run(os.path.join(HERE, "web_icons.py"))
run(os.path.join(SK, "presentation_board.py"), os.path.join(HERE, "presentation-spec.json"), "-o", "presentation.html")
