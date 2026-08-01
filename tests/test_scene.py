import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scene import _camera_transform, capture_scene


class FakeModels:
    def __init__(self, models):
        self._models = models

    def list(self, type=None):
        return self._models


class FakeSession:
    def __init__(self, models):
        self.models = FakeModels(models)
        self.main_view = None


class FakeModel:
    name = "model"

    def __init__(self, atoms, display=True, parents_displayed=True):
        self.atoms = atoms
        self.display = display
        self.parents_displayed = parents_displayed


class FakeChain:
    chain_id = "A"


class FakeResidue:
    PT_NONE = 0

    def __init__(
        self, ribbon_display=False, ribbon_color=(0, 255, 0, 255),
        polymer_type=1,
    ):
        self.number = 42
        self.chain = FakeChain()
        self.ribbon_display = ribbon_display
        self.ribbon_color = ribbon_color
        self.polymer_type = polymer_type


class FakeElement:
    def __init__(self, number, name):
        self.number = number
        self.name = name


class FakeAtom:
    def __init__(
        self, display, ribbon_display=False, scene_coord=None,
        color=(255, 0, 0, 255), polymer_type=1, element=None,
    ):
        self.display = display
        self.visible = display
        self.coord = (1.0, 2.0, 3.0)
        if scene_coord is not None:
            self.scene_coord = scene_coord
        self.color = color
        self.radius = 1.5
        self.element = element or FakeElement(6, "C")
        self.residue = FakeResidue(
            ribbon_display=ribbon_display,
            polymer_type=polymer_type,
        )
        self.name = "CA"


class FakeSurface:
    def __init__(
        self, atoms, color=(0, 0, 255, 255), display=True,
        parents_displayed=True,
    ):
        self.atoms = atoms
        self.show_atoms = atoms
        self.overall_color = color
        self.display = display
        self.parents_displayed = parents_displayed


class FakePlace:
    def __init__(self, matrix, inverse_matrix=None):
        self._matrix = matrix
        self._inverse_matrix = inverse_matrix

    @property
    def matrix(self):
        return self._matrix

    def inverse(self):
        if self._inverse_matrix is None:
            return self
        return FakePlace(self._inverse_matrix)


class FakeCamera:
    name = "orthographic"

    def __init__(self, position_matrix, inverse_matrix):
        self.position = FakePlace(position_matrix, inverse_matrix)


class CameraTransformTests(unittest.TestCase):
    def test_camera_transform_transposes_place_matrix_for_renderer(self):
        inverse_matrix = (
            (0.0, -1.0, 0.0, 10.0),
            (1.0, 0.0, 0.0, 20.0),
            (0.0, 0.0, 1.0, 30.0),
        )
        position_matrix = (
            (0.0, 1.0, 0.0, -20.0),
            (-1.0, 0.0, 0.0, 10.0),
            (0.0, 0.0, 1.0, -30.0),
        )
        rotation, translation = _camera_transform(FakeCamera(position_matrix, inverse_matrix))
        self.assertEqual(rotation, (
            (0.0, -1.0, 0.0),
            (-1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
        ))
        self.assertEqual(translation, (10.0, -20.0, 30.0))


class SceneCaptureTests(unittest.TestCase):
    def test_hidden_atoms_are_not_captured_and_reported(self):
        session = FakeSession([FakeModel([FakeAtom(display=False)])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms, ())
        self.assertIn("没有可捕获", warning)

    def test_visible_atom_metadata_is_captured(self):
        session = FakeSession([FakeModel([FakeAtom(display=True)])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        atom = scene.atoms[0]
        self.assertEqual(atom.coord, (1.0, 2.0, 3.0))
        self.assertEqual(atom.color, (1.0, 0.0, 0.0))
        self.assertEqual(atom.radius, 1.5)
        self.assertEqual(atom.subunit, "model:A")
        self.assertEqual(atom.residue, 42)
        self.assertEqual(warning, "")

    def test_cartoon_residue_captures_hidden_atoms_with_ribbon_color(self):
        atom = FakeAtom(display=False, ribbon_display=True)
        session = FakeSession([FakeModel([atom])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        self.assertEqual(scene.atoms[0].color, (0.0, 1.0, 0.0))
        self.assertEqual(warning, "")

    def test_palette_atom_colors_override_cartoon_color(self):
        atom = FakeAtom(display=False, ribbon_display=True)
        session = FakeSession([FakeModel([atom])])
        session._illustrate_prefer_atom_colors = True
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        self.assertEqual(scene.atoms[0].color, (1.0, 0.0, 0.0))
        self.assertEqual(warning, "")

    def test_nonpolymer_ribbon_flag_does_not_capture_hidden_atoms(self):
        atom = FakeAtom(
            display=False,
            ribbon_display=True,
            polymer_type=FakeResidue.PT_NONE,
        )
        session = FakeSession([FakeModel([atom])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms, ())
        self.assertIn("没有可捕获", warning)

    def test_hidden_hydrogen_is_not_reintroduced_by_cartoon(self):
        atom = FakeAtom(
            display=False,
            ribbon_display=True,
            element=FakeElement(1, "H"),
        )
        session = FakeSession([FakeModel([atom])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms, ())
        self.assertIn("没有可捕获", warning)

    def test_explicitly_displayed_hydrogen_is_captured(self):
        atom = FakeAtom(display=True, element=FakeElement(1, "H"))
        session = FakeSession([FakeModel([atom])])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        self.assertEqual(warning, "")

    def test_visible_surface_captures_its_associated_hidden_atoms(self):
        atom = FakeAtom(display=False)
        model = FakeModel([atom])
        surface = FakeSurface([atom])
        session = FakeSession([model, surface])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        self.assertEqual(scene.atoms[0].color, (0.0, 0.0, 1.0))
        self.assertEqual(warning, "")

    def test_palette_atom_colors_override_surface_color(self):
        atom = FakeAtom(display=False)
        model = FakeModel([atom])
        surface = FakeSurface([atom])
        session = FakeSession([model, surface])
        session._illustrate_prefer_atom_colors = True
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(len(scene.atoms), 1)
        self.assertEqual(scene.atoms[0].color, (1.0, 0.0, 0.0))
        self.assertEqual(warning, "")

    def test_hidden_surface_does_not_capture_atoms(self):
        atom = FakeAtom(display=False)
        session = FakeSession([
            FakeModel([atom]),
            FakeSurface([atom], display=False),
        ])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms, ())
        self.assertIn("没有可捕获", warning)

    def test_hidden_atomic_model_is_not_captured(self):
        atom = FakeAtom(display=True)
        session = FakeSession([FakeModel([atom], display=False)])
        scene, _view, _style, warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms, ())
        self.assertIn("没有可捕获", warning)

    def test_explicit_atom_color_takes_priority_over_surface_color(self):
        atom = FakeAtom(display=True)
        session = FakeSession([FakeModel([atom]), FakeSurface([atom])])
        scene, _view, _style, _warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms[0].color, (1.0, 0.0, 0.0))

    def test_scene_coordinates_include_model_transform(self):
        atom = FakeAtom(
            display=True,
            scene_coord=(11.0, 12.0, 13.0),
        )
        session = FakeSession([FakeModel([atom])])
        scene, _view, _style, _warning = capture_scene(session, 80, 80)
        self.assertEqual(scene.atoms[0].coord, (11.0, 12.0, 13.0))


if __name__ == "__main__":
    unittest.main()
