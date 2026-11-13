import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_probe import FakeApp


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "EasyCraftGen.PspScript"


def load_script(app):
    psp = types.ModuleType("PSPApp")
    psp.App = app
    namespace = {}
    with patch.dict(sys.modules, {"PSPApp": psp}):
        exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), namespace)
    return namespace


class IntegrationScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = self.temp.name

    def run_script(self, app, child):
        namespace = load_script(app)
        namespace["run_easycraftgen"] = child
        with patch.object(namespace["tempfile"], "mkdtemp", return_value=self.folder):
            namespace["Do"]("environment")
        return app.calls

    def test_selected_result_is_pasted_and_masked(self):
        app = FakeApp(selection="normal")
        def child(folder, width, height, bounds):
            self.assertEqual((128, 64, [12, 20, 38, 20]), (width, height, bounds))
            pathlib.Path(folder, "result.png").write_bytes(b"result")
            return "success"
        calls = self.run_script(app, child)
        commands = [call[1] for call in calls]
        self.assertIn("PasteAsNewLayer", commands)
        self.assertIn("SelectLoadDisk", commands)
        self.assertIn("MaskShowSelection", commands)
        self.assertNotIn("NegativeImage", commands)
        self.assertEqual(2, commands.count("GetRasterSelectionRect"))

    def test_no_selection_is_unmasked(self):
        app = FakeApp()
        def child(folder, width, height, bounds):
            self.assertIsNone(bounds)
            pathlib.Path(folder, "result.png").write_bytes(b"result")
            return "success"
        commands = [call[1] for call in self.run_script(app, child)]
        self.assertIn("PasteAsNewLayer", commands)
        self.assertNotIn("SelectSaveDisk", commands)
        self.assertNotIn("MaskShowSelection", commands)

    def test_cancel_does_not_open_or_paste_result(self):
        app = FakeApp(selection="normal")
        commands = [call[1] for call in self.run_script(app, lambda *args: "cancelled")]
        self.assertNotIn("FileOpen", commands)
        self.assertNotIn("PasteAsNewLayer", commands)
        self.assertIn("cancelled", app.calls[-1][2]["Text"])

    def test_failure_does_not_paste(self):
        app = FakeApp()
        def fail(*args):
            raise RuntimeError("child failure")
        with self.assertRaisesRegex(RuntimeError, "child failure"):
            self.run_script(app, fail)
        self.assertIn("running EasyCraftGen", app.calls[-1][2]["Text"])
        self.assertNotIn("PasteAsNewLayer", [call[1] for call in app.calls])

    def test_changed_selection_does_not_paste(self):
        app = FakeApp(selection="normal")
        def child(*args):
            app.selection = "none"
            return "success"
        with self.assertRaisesRegex(RuntimeError, "selection changed"):
            self.run_script(app, child)
        self.assertNotIn("PasteAsNewLayer", [call[1] for call in app.calls])

    def test_bounds_accept_mapping_and_reject_invalid(self):
        bounds = load_script(FakeApp())["selection_bounds"]
        self.assertEqual([12, 20, 38, 20], bounds(
            {"Rect": {"Left": 12, "Top": 20, "Right": 50, "Bottom": 40}}, 128, 64))
        for rect in ((0, 0, 200, 10), (1, 1, 1, 5), (1, 2, 3)):
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                bounds({"Rect": rect}, 128, 64)

    def test_psp_nested_rectangle_with_float_coordinates(self):
        bounds = load_script(FakeApp())["selection_bounds"]
        self.assertEqual([760, 1148, 1026, 1013],
                         bounds({"Rect": ((760.0, 1148.0), 1026.0, 1013.0)}, 3000, 3000))
        self.assertEqual([12, 20, 39, 21],
                         bounds({"Rect": ((12.25, 20.25), 38.25, 20.25)}, 128, 64))

    def test_psp_nested_rectangle_rejects_bad_values(self):
        bounds = load_script(FakeApp())["selection_bounds"]
        for rect in (((1, 2), 0, 3), ((-1, 2), 4, 3), ((120, 0), 9, 3),
                     ((1, 2), float("nan"), 3), ((1, 2), float("inf"), 3),
                     ((1, 2), True, 3), ((1,), 4, 3)):
            with self.subTest(rect=rect), self.assertRaises((ValueError, TypeError)):
                bounds({"Rect": rect}, 128, 64)

    def test_psp_nested_rectangle_passes_integer_job_bounds(self):
        app = FakeApp(selection="normal")
        original_do = app.Do
        def do(environment, command, params=None, target=None):
            result = original_do(environment, command, params, target)
            if command == "GetRasterSelectionRect":
                return {"Type": app.selection, "Rect": ((12.0, 20.0), 38.0, 20.0)}
            return result
        app.Do = do
        def child(folder, width, height, bounds):
            self.assertEqual([12, 20, 38, 20], bounds)
            self.assertTrue(all(type(value) is int for value in bounds))
            pathlib.Path(folder, "result.png").write_bytes(b"result")
            return "success"
        commands = [call[1] for call in self.run_script(app, child)]
        self.assertIn("MaskShowSelection", commands)

    def test_child_contract_and_missing_success_result(self):
        namespace = load_script(FakeApp())
        executable = pathlib.Path(self.folder, "EasyCraftGen.exe")
        executable.write_bytes(b"")
        namespace["EASYCRAFTGEN_EXE"] = str(executable)
        def launch(args):
            self.assertEqual([str(executable), "--psp-job", os.path.join(self.folder, "request.json")], args)
            request = json.loads(pathlib.Path(args[2]).read_text())
            self.assertEqual({"version": 1, "width": 128, "height": 64, "selection": [12, 20, 38, 20]}, request)
            pathlib.Path(self.folder, "response.json").write_text('{"version":1,"status":"success"}')
            return types.SimpleNamespace(wait=lambda: 0)
        with patch.object(namespace["subprocess"], "Popen", side_effect=launch):
            with self.assertRaisesRegex(RuntimeError, "without a result"):
                namespace["run_easycraftgen"](self.folder, 128, 64, [12, 20, 38, 20])
            pathlib.Path(self.folder, "result.png").write_bytes(b"image")
            self.assertEqual("success", namespace["run_easycraftgen"](self.folder, 128, 64, [12, 20, 38, 20]))

    def test_child_cancel_and_bad_exit_or_response(self):
        namespace = load_script(FakeApp())
        executable = pathlib.Path(self.folder, "EasyCraftGen.exe")
        executable.write_bytes(b"")
        namespace["EASYCRAFTGEN_EXE"] = str(executable)
        response = pathlib.Path(self.folder, "response.json")
        with patch.object(namespace["subprocess"], "Popen", return_value=types.SimpleNamespace(wait=lambda: 0)):
            with self.assertRaisesRegex(RuntimeError, "without reporting"):
                namespace["run_easycraftgen"](self.folder, 128, 64, None)
            response.write_text('{"version":1,"status":"cancelled"}')
            self.assertEqual("cancelled", namespace["run_easycraftgen"](self.folder, 128, 64, None))
            response.write_text('{"version":2,"status":"success"}')
            with self.assertRaisesRegex(RuntimeError, "invalid response"):
                namespace["run_easycraftgen"](self.folder, 128, 64, None)
        with patch.object(namespace["subprocess"], "Popen", return_value=types.SimpleNamespace(wait=lambda: 3)):
            with self.assertRaisesRegex(RuntimeError, "code 3"):
                namespace["run_easycraftgen"](self.folder, 128, 64, None)


if __name__ == "__main__":
    unittest.main()
