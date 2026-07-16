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
    display = True
    name = "model"

    def __init__(self, atoms):
        self.atoms = atoms


class FakeChain:
    chain_id = "A"


class FakeResidue:
    number = 42
    chain = FakeChain()


class FakeAtom:
    def __init__(self, display):
        self.display = display
        self.coord = (1.0, 2.0, 3.0)
        self.color = (255, 0, 0, 255)
        self.radius = 1.5
        self.residue = FakeResidue()
        self.name = "CA"


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
        self.assertIn("没有可见原子球体", warning)

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


if __name__ == "__main__":
    unittest.main()
