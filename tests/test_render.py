import os
import struct
import sys
import tempfile
import unittest
import zlib
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import render as render_module
from render import (
    AtomRecord,
    IllustrationStyle,
    RenderScene,
    ViewSnapshot,
    _contour_thresholds,
    encode_png,
    render,
    save_png,
    scale_style_for_output,
)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.scene = RenderScene((
            AtomRecord((0.0, 0.0, 0.0), (1.0, 0.2, 0.2), 1.5, "model:A", 1, "CA"),
            AtomRecord((2.5, 0.0, 0.0), (0.2, 0.2, 1.0), 1.2, "model:B", 2, "CA"),
        ))
        self.view = ViewSnapshot(pixels_per_angstrom=18.0, auto_center=True)
        self.style = IllustrationStyle(shadows=False)

    def test_render_has_opaque_atom_and_transparent_background(self):
        image = render(self.scene, self.view, self.style, 80, 80)
        self.assertEqual((image.width, image.height), (80, 80))
        alphas = image.rgba[3::4]
        self.assertIn(255, alphas)
        self.assertIn(0, alphas)

    def test_view_rotation_changes_projection(self):
        image_a = render(self.scene, self.view, self.style, 80, 80)
        rotated = ViewSnapshot(
            rotation=((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            pixels_per_angstrom=18.0,
            auto_center=True,
        )
        image_b = render(self.scene, rotated, self.style, 80, 80)
        self.assertNotEqual(image_a.rgba, image_b.rgba)

    def test_style_controls_change_render(self):
        image_a = render(self.scene, self.view, self.style, 48, 48)
        styled = IllustrationStyle(shadows=True, fog_back=0.5, contour_high=1.0)
        image_b = render(self.scene, self.view, styled, 48, 48)
        self.assertNotEqual(image_a.rgba, image_b.rgba)

    def test_numpy_and_python_backends_both_render(self):
        if render_module._np is None:
            self.skipTest("NumPy is not available")
        style = scale_style_for_output(
            IllustrationStyle(shadows=False), 96, 64
        )
        view = replace(self.view, pixels_per_angstrom=27.0)
        accelerated = render(self.scene, view, style, 96, 96)
        reference = render_module._render_python(self.scene, view, style, 96, 96)
        self.assertIn(255, accelerated.rgba[3::4])
        self.assertIn(255, reference.rgba[3::4])
        self.assertEqual(accelerated.rgba, reference.rgba)

    def test_sphere_samples_are_cached_by_radius(self):
        render_module._sphere_points.cache_clear()
        first = render_module._sphere_points(12.5)
        second = render_module._sphere_points(12.5)
        self.assertIs(first, second)
        self.assertGreater(len(first), 0)

    def test_numpy_opaque_compositing_matches_integer_reference(self):
        if render_module._np is None:
            self.skipTest("NumPy is not available")
        image = render(self.scene, self.view, self.style, 24, 24)
        accelerated = image.composited_rgba(transparent=False)
        expected = bytearray(len(image.rgba))
        background = tuple(
            int(round(channel * 255.0)) for channel in image.background
        )
        for index in range(0, len(image.rgba), 4):
            alpha = image.rgba[index + 3]
            inverse = 255 - alpha
            for channel in range(3):
                expected[index + channel] = (
                    image.rgba[index + channel] * alpha
                    + background[channel] * inverse
                ) // 255
            expected[index + 3] = 255
        self.assertEqual(accelerated, bytes(expected))

    def test_contours_darken_rgb_toward_black(self):
        style = IllustrationStyle(
            shadows=False,
            contour_low=0.0,
            contour_high=0.0001,
            contour_depth_min=0.0,
            contour_depth_max=1.0,
        )
        image = render(self.scene, self.view, style, 80, 80)
        pixels = [
            image.rgba[index:index + 4]
            for index in range(0, len(image.rgba), 4)
        ]
        outlined = [pixel for pixel in pixels if pixel[3] > 0 and pixel[:3] == b"\x00\x00\x00"]
        self.assertTrue(outlined)

    def test_transparent_and_opaque_png_encodings_are_valid(self):
        image = render(self.scene, self.view, self.style, 24, 24)
        for transparent in (True, False):
            png = encode_png(image, transparent=transparent)
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(png[12:16], b"IHDR")
            width, height = struct.unpack(">II", png[16:24])
            self.assertEqual((width, height), (24, 24))
            compressed = bytearray()
            offset = 8
            while offset < len(png):
                size = struct.unpack(">I", png[offset:offset + 4])[0]
                kind = png[offset + 4:offset + 8]
                data = png[offset + 8:offset + 8 + size]
                offset += size + 12
                if kind == b"IDAT":
                    compressed.extend(data)
            raw = zlib.decompress(bytes(compressed))
            self.assertEqual(len(raw), (24 * 4 + 1) * 24)
            if not transparent:
                pixels = bytearray()
                stride = 24 * 4
                for row in range(24):
                    start = row * (stride + 1) + 1
                    pixels.extend(raw[start:start + stride])
                self.assertTrue(all(alpha == 255 for alpha in pixels[3::4]))

    def test_streamed_png_matches_encoded_pixels(self):
        image = render(self.scene, self.view, self.style, 24, 24)
        for transparent in (True, False):
            expected = encode_png(image, transparent=transparent)
            with tempfile.NamedTemporaryFile(suffix=".png") as output:
                save_png(output.name, image, transparent=transparent)
                output.seek(0)
                streamed = output.read()
            self.assertEqual(
                self._decode_png_rgba(streamed),
                self._decode_png_rgba(expected),
            )

    def test_empty_scene_is_a_valid_image(self):
        image = render(RenderScene(()), self.view, self.style, 8, 8)
        self.assertEqual(set(image.rgba[3::4]), {0})

    def test_default_contour_kernel_matches_reference_input(self):
        self.assertEqual(IllustrationStyle().contour_kernel, 4)

    def test_default_outline_parameters_match_reference_input(self):
        style = IllustrationStyle()
        self.assertEqual(
            (style.contour_low, style.contour_high, style.contour_kernel,
             style.contour_depth_min, style.contour_depth_max),
            (3.0, 10.0, 4, 0.0, 5.0),
        )

    def test_default_shading_and_residue_parameters_match_reference_input(self):
        style = IllustrationStyle()
        self.assertEqual(style.shadow_maximum, 0.7)
        self.assertEqual(style.residue_difference, 6.0)

    def test_output_size_scales_pixel_based_thresholds(self):
        style = IllustrationStyle(
            contour_low=3.0,
            contour_high=10.0,
            contour_kernel=1,
            contour_depth_min=0.5,
            contour_depth_max=5.0,
            shadow_depth=1.0,
        )
        scaled = scale_style_for_output(style, 1200, 320)
        self.assertEqual(scaled.contour_low, 11.25)
        self.assertEqual(scaled.contour_high, 37.5)
        self.assertEqual(scaled.contour_depth_min, 1.875)
        self.assertEqual(scaled.contour_depth_max, 18.75)
        self.assertEqual(scaled.shadow_depth, 3.75)
        self.assertEqual(scaled.subunit_low, style.subunit_low)
        self.assertEqual(scaled.raster_scale, 1.0)
        self.assertEqual(scale_style_for_output(style, 4000, 320).raster_scale,
                         4000.0 / 1200.0)

    def test_count_based_contour_kernels_keep_dimensionless_thresholds(self):
        kernel_three = replace(self.style, contour_kernel=3)
        kernel_four = replace(self.style, contour_kernel=4)
        scaled_three = scale_style_for_output(kernel_three, 4000, 320)
        scaled_four = scale_style_for_output(kernel_four, 4000, 320)
        self.assertEqual((scaled_three.contour_low, scaled_three.contour_high), (3.0, 10.0))
        self.assertEqual((scaled_four.contour_low, scaled_four.contour_high), (3.0, 10.0))
        self.assertEqual(_contour_thresholds(kernel_three), (1.5, 5.0))
        self.assertEqual(_contour_thresholds(kernel_four), (6.0, 20.0))

    def test_all_contour_kernels_keep_the_scene_visible(self):
        for kernel in (1, 2, 3, 4):
            style = replace(self.style, contour_kernel=kernel)
            image = render(
                self.scene,
                self.view,
                scale_style_for_output(style, 96, 64),
                96,
                96,
            )
            self.assertIn(255, image.rgba[3::4], "kernel %d" % kernel)

    def test_rotated_scene_remains_visible_when_depth_is_below_legacy_sentinel(self):
        view = ViewSnapshot(
            translation=(0.0, 0.0, -200.0),
            pixels_per_angstrom=100.0,
            auto_center=False,
        )
        image = render(self.scene, view, self.style, 256, 256)
        self.assertIn(255, image.rgba[3::4])

    def test_scaled_render_produces_valid_images(self):
        """The legacy renderer remains valid at preview and export sizes."""

        low_size = 64
        high_size = 192
        # Kernel 1 is the known-good default used by the 0.1.6 renderer.
        style = replace(self.style, contour_kernel=1, shadows=True)
        low = render(
            self.scene,
            self.view,
            scale_style_for_output(
                style, low_size, low_size,
            ),
            low_size,
            low_size,
        )
        high = render(
            self.scene,
            replace(self.view, pixels_per_angstrom=self.view.pixels_per_angstrom * 3.0),
            scale_style_for_output(
                style, high_size, low_size,
            ),
            high_size,
            high_size,
        )
        self.assertIn(255, low.rgba[3::4])
        self.assertIn(255, high.rgba[3::4])

    @staticmethod
    def _decode_png_rgba(png):
        width, height = struct.unpack(">II", png[16:24])
        compressed = bytearray()
        offset = 8
        while offset < len(png):
            size = struct.unpack(">I", png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            data = png[offset + 8:offset + 8 + size]
            offset += size + 12
            if kind == b"IDAT":
                compressed.extend(data)
        raw = zlib.decompress(bytes(compressed))
        row_bytes = width * 4
        pixels = bytearray()
        for row in range(height):
            start = row * (row_bytes + 1)
            self_filter = raw[start]
            if self_filter != 0:
                raise AssertionError("unexpected PNG filter")
            pixels.extend(raw[start + 1:start + 1 + row_bytes])
        return bytes(pixels)


if __name__ == "__main__":
    unittest.main()
