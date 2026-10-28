import sys, pymupdf, io
d = pymupdf.open(sys.argv[1])
out = io.open(sys.argv[2], "w", encoding="utf-8")
out.write(f"PAGINE {len(d)}\n")
for i, p in enumerate(d):
    out.write(f"\n======== PAG {i+1} ========\n")
    out.write(p.get_text())
