"""Isolated parser worker for already malware-scanned evidence documents.

This file is executed directly with Python isolated mode. It deliberately has
no CareSync imports, database access, network logic, or write path.
"""

from __future__ import annotations

import resource
import sys
import warnings
from pathlib import Path

MAX_PDF_GRAPH_OBJECTS = 10_000
MAX_PDF_GRAPH_DEPTH = 64
ACTIVE_KEYS = {
    "/A",
    "/AA",
    "/OpenAction",
    "/JavaScript",
    "/JS",
    "/Launch",
    "/EmbeddedFiles",
    "/Filespec",
    "/EF",
    "/RichMediaContent",
    "/AF",
    "/Collection",
    "/AcroForm",
    "/XFA",
}
ACTIVE_ACTION_TYPES = {
    "/JavaScript",
    "/Launch",
    "/SubmitForm",
    "/ImportData",
    "/GoToR",
    "/Rendition",
    "/RichMediaExecute",
}
ACTIVE_ANNOTATION_TYPES = {
    "/FileAttachment",
    "/RichMedia",
    "/Screen",
    "/Movie",
    "/Sound",
    "/3D",
}


class UnsafeDocument(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _walk_pdf_graph(root: object) -> None:
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    stack: list[tuple[object, int]] = [(root, 0)]
    visited_indirect: set[tuple[int, int]] = set()
    visited_direct: set[int] = set()
    count = 0
    while stack:
        value, depth = stack.pop()
        if depth > MAX_PDF_GRAPH_DEPTH:
            raise UnsafeDocument("pdf_structure_limit")
        if isinstance(value, IndirectObject):
            identity = (value.idnum, value.generation)
            if identity in visited_indirect:
                continue
            visited_indirect.add(identity)
            value = value.get_object()
        elif isinstance(value, (DictionaryObject, ArrayObject)):
            identity = id(value)
            if identity in visited_direct:
                continue
            visited_direct.add(identity)
        else:
            continue
        count += 1
        if count > MAX_PDF_GRAPH_OBJECTS:
            raise UnsafeDocument("pdf_structure_limit")
        if isinstance(value, DictionaryObject):
            keys = {str(key) for key in value}
            if keys & ACTIVE_KEYS:
                raise UnsafeDocument("active_evidence_pdf")
            if str(value.get("/S")) in ACTIVE_ACTION_TYPES:
                raise UnsafeDocument("active_evidence_pdf")
            if str(value.get("/Subtype")) in ACTIVE_ANNOTATION_TYPES:
                raise UnsafeDocument("active_evidence_pdf")
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, ArrayObject):
            stack.extend((child, depth + 1) for child in value)


def _validate_pdf(path: Path, maximum_pages: int) -> None:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        with path.open("rb") as source:
            reader = PdfReader(source)
            if reader.is_encrypted:
                raise UnsafeDocument("encrypted_evidence_pdf")
            pages = len(reader.pages)
            if pages < 1 or pages > maximum_pages:
                raise UnsafeDocument("evidence_pdf_page_limit")
            _walk_pdf_graph(reader.root_object)
    except UnsafeDocument:
        raise
    except (PyPdfError, OSError, ValueError, IndexError, KeyError, SyntaxError):
        raise UnsafeDocument("invalid_evidence_document") from None


def _validate_image(path: Path, media_type: str, maximum_pixels: int) -> None:
    from PIL import Image, UnidentifiedImageError

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                expected = "PNG" if media_type == "image/png" else "JPEG"
                if image.format != expected:
                    raise UnsafeDocument("evidence_media_mismatch")
                if image.width * image.height > maximum_pixels:
                    raise UnsafeDocument("evidence_image_pixel_limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise UnsafeDocument("animated_evidence_image")
                image.verify()
    except UnsafeDocument:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UnsafeDocument("evidence_image_pixel_limit") from None
    except (UnidentifiedImageError, OSError, ValueError, IndexError, KeyError, SyntaxError):
        raise UnsafeDocument("invalid_evidence_document") from None


def _apply_limits(cpu_seconds: int, address_space: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    _, nofile_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    nofile_limit = 32 if nofile_hard == resource.RLIM_INFINITY else min(32, nofile_hard)
    resource.setrlimit(resource.RLIMIT_NOFILE, (nofile_limit, nofile_limit))
    if hasattr(resource, "RLIMIT_AS"):
        # Darwin maps the shared cache into a very large virtual address range;
        # a conventional 1 GiB RLIMIT_AS is below the interpreter's baseline.
        if sys.platform == "darwin":
            address_space = max(address_space, 16 * 1024**4)
        _, address_hard = resource.getrlimit(resource.RLIMIT_AS)
        address_limit = (
            address_space
            if address_hard == resource.RLIM_INFINITY
            else min(address_space, address_hard)
        )
        resource.setrlimit(resource.RLIMIT_AS, (address_limit, address_limit))


def main() -> int:
    if len(sys.argv) != 7:
        return 3
    path = Path(sys.argv[1])
    media_type = sys.argv[2]
    try:
        maximum_pixels = int(sys.argv[3])
        maximum_pages = int(sys.argv[4])
        cpu_seconds = int(sys.argv[5])
        address_space = int(sys.argv[6])
        _apply_limits(cpu_seconds, address_space)
        if media_type == "application/pdf":
            _validate_pdf(path, maximum_pages)
        elif media_type in {"image/png", "image/jpeg"}:
            _validate_image(path, media_type, maximum_pixels)
        else:
            raise UnsafeDocument("unsupported_evidence_media")
    except UnsafeDocument as error:
        print(error.code)
        return 2
    except (OSError, ValueError):
        print("invalid_evidence_document")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
