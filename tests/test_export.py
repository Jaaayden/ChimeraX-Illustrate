import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from src.export import (
    LARGE_EXPORT_PIXELS,
    EXPORT_PRESET_SIZES,
    MAX_OUTPUT_SIZE,
    ExportError,
    check_output_size,
    default_export_filename,
    estimated_memory_gb,
    filename_stem,
    export_png,
    is_large_export,
    render_snapshot_to_png,
    snapshot_name,
)
from src.render import (
    AtomRecord,
    IllustrationStyle,
    RenderScene,
    ViewSnapshot,
    view_for_size,
)
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

    def test_limits_are_consistent(self):
        self.assertGreaterEqual(MAX_OUTPUT_SIZE, 16000)
        self.assertIn(1200, EXPORT_PRESET_SIZES)
        self.assertEqual(list(EXPORT_PRESET_SIZES), sorted(EXPORT_PRESET_SIZES))
        self.assertLessEqual(max(EXPORT_PRESET_SIZES), MAX_OUTPUT_SIZE)

    def test_large_export_notice_and_memory_estimate(self):
        self.assertFalse(is_large_export(1200, 1200))
        self.assertFalse(is_large_export(6000, 6000))
        self.assertTrue(is_large_export(6001, 6000))
        self.assertGreater(LARGE_EXPORT_PIXELS, 1200 * 1200)
        # A 16000 x 16000 image needs several GB; a 1200 x 1200 one well under 1.
        self.assertGreater(estimated_memory_gb(16000, 16000), 5.0)
        self.assertLess(estimated_memory_gb(1200, 1200), 0.1)

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


class NamingTests(unittest.TestCase):
    @staticmethod
    def _model(name, **kwargs):
        model = FakeModel([FakeAtom(display=True)], **kwargs)
        model.name = name
        return model

    def test_stem_drops_structure_extensions_and_unsafe_characters(self):
        self.assertEqual(filename_stem("1abc"), "1abc")
        self.assertEqual(filename_stem("1abc.cif"), "1abc")
        self.assertEqual(filename_stem("my model.pdb.gz"), "my_model")
        self.assertEqual(filename_stem("a/b:c*?.pdb"), "a_b_c")
        self.assertEqual(filename_stem("\u86cb\u767d\u8d28.pdb"), "\u86cb\u767d\u8d28")
        self.assertEqual(filename_stem(".pdb"), "pdb")
        self.assertEqual(filename_stem("???"), "")
        self.assertLessEqual(len(filename_stem("x" * 200)), 60)

    def test_snapshot_name_uses_the_visible_structure(self):
        session = FakeSession([self._model("1abc.cif")])
        self.assertEqual(snapshot_name(session), "1abc")

    def test_snapshot_name_summarizes_several_structures(self):
        session = FakeSession([self._model("1abc"), self._model("2xyz"), self._model("3def")])
        self.assertEqual(snapshot_name(session), "1abc_plus2")

    def test_hidden_structures_do_not_name_the_snapshot(self):
        session = FakeSession([
            self._model("hidden", display=False), self._model("shown"),
        ])
        self.assertEqual(snapshot_name(session), "shown")

    def test_snapshot_name_falls_back_when_nothing_is_shown(self):
        self.assertEqual(snapshot_name(FakeSession([])), "illustrate")
        self.assertEqual(snapshot_name(FakeSession([self._model("???")])), "illustrate")

    def test_default_filename_includes_the_size(self):
        self.assertEqual(default_export_filename("1abc", 1200, 1200), "1abc_1200x1200.png")
        self.assertEqual(default_export_filename("", 600, 300), "illustrate_600x300.png")


if __name__ == "__main__":
    unittest.main()
