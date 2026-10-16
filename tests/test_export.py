import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.export import (
    MAX_OUTPUT_SIZE,
    ExportError,
    check_output_size,
    export_png,
    render_snapshot_to_png,
    view_for_size,
)
from src.render import AtomRecord, IllustrationStyle, RenderScene, ViewSnapshot
from test_scene import FakeAtom, FakeModel, FakeSession


def png_size(path):
    with open(path, "rb") as handle:
        data = handle.read(24)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


class OutputSizeTests(unittest.TestCase):
    def test_check_output_size_reports_the_violated_limit(self):
        self.assertIsNone(check_output_size(2, 2))
        self.assertIsNone(check_output_size(MAX_OUTPUT_SIZE, MAX_OUTPUT_SIZE))
        self.assertEqual(check_output_size(1, 500), "minimum_size")
        self.assertEqual(check_output_size(500, 1), "minimum_size")
        self.assertEqual(check_output_size(MAX_OUTPUT_SIZE + 1, 500), "maximum_size")

    def test_view_scales_with_output_width(self):
        view = ViewSnapshot(pixels_per_angstrom=10.0)
        self.assertEqual(view_for_size(view, 1024, 512).pixels_per_angstrom, 20.0)
        self.assertEqual(view_for_size(view, 512, 512).pixels_per_angstrom, 10.0)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.scene = RenderScene((
            AtomRecord((0.0, 0.0, 0.0), (1.0, 0.2, 0.2), 1.5, "m:A", 1, "CA"),
        ))
        self.view = ViewSnapshot(pixels_per_angstrom=18.0, auto_center=True)

    def test_render_snapshot_to_png_writes_requested_size(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "out.png")
            result = render_snapshot_to_png(
                self.scene, self.view, IllustrationStyle(), 64, 96, 80, path,
            )
            self.assertEqual(result, path)
            self.assertEqual(png_size(path), (96, 80))

    def test_export_png_is_synchronous_and_complete_on_return(self):
        session = FakeSession([FakeModel([FakeAtom(display=True)])])
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "scene.png")
            returned, warnings = export_png(
                session, path, transparent=False, width=120, height=90,
            )
            self.assertEqual(returned, path)
            self.assertEqual(warnings, ())
            self.assertEqual(png_size(path), (120, 90))

    def test_export_png_rejects_an_empty_scene(self):
        session = FakeSession([FakeModel([FakeAtom(display=False)])])
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "empty.png")
            with self.assertRaises(ExportError):
                export_png(session, path)
            self.assertFalse(os.path.exists(path))

    def test_export_png_rejects_invalid_sizes_before_capturing(self):
        session = FakeSession([FakeModel([FakeAtom(display=True)])])
        for size in (1, MAX_OUTPUT_SIZE + 1):
            with self.subTest(size=size):
                with self.assertRaises(ExportError):
                    export_png(session, "unused.png", width=size, height=size)


if __name__ == "__main__":
    unittest.main()
