import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "EasyCraftGen Probe.PspScript"


def document(name):
    return types.SimpleNamespace(Name=name, Title=name, Width=128, Height=64)


class FakeApp:
    Constants = types.SimpleNamespace(
        MsgButtons=types.SimpleNamespace(OK="ok", YesNo="yesno"),
        MsgIcons=types.SimpleNamespace(Stop="stop", Question="question"),
        SelectionType=types.SimpleNamespace(Floating="floating", **{"None": "none"}),
        Boolean=types.SimpleNamespace(**{"false": False}),
        ExecutionMode=types.SimpleNamespace(Silent="silent"),
        FileFormat=types.SimpleNamespace(PNG="png"),
        SelectionOperation=types.SimpleNamespace(Replace="replace"),
        CreateMaskFrom=types.SimpleNamespace(Luminance="luminance"),
    )

    def __init__(self, selection="none", choice=1, fail_on=None, with_document=True, layers=2):
        self.TargetDocument = document("original") if with_document else None
        self.Documents = [self.TargetDocument] if with_document else []
        self.selection = selection
        self.choice = choice
        self.fail_on = fail_on
        self.layers = layers
        self.calls = []

    def Do(self, environment, command, params=None, target=None):
        self.calls.append((environment, command, params, target))
        if command == self.fail_on:
            raise RuntimeError("Simulated host failure")
        if command == "GetRasterSelectionRect":
            return {"Type": self.selection, "Rect": (12, 20, 50, 40)}
        if command == "MsgBox":
            return self.choice
        if command == "SelectSaveDisk":
            name = params["FileName"]
            if os.path.basename(name) != name or "." in name:
                raise ValueError("Selection name must be a plain name")
            self.saved_selection = name
        if command == "SelectLoadDisk":
            if params["FileName"] != self.saved_selection:
                raise ValueError("Selection name does not match")
        if command == "DuplicateWindow":
            self.Documents.append(document("duplicate"))
        if command == "ReturnImageInfo":
            return {"LayerNum": self.layers}
        if command == "FileSaveAs":
            pathlib.Path(params["FileName"]).write_bytes(b"png")
        if command == "FileOpen":
            self.Documents.append(document("opened"))


def run_probe(app, folder, child=None):
    psp = types.ModuleType("PSPApp")
    psp.App = app
    namespace = {}
    with patch.dict(sys.modules, {"PSPApp": psp}):
        exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), namespace)
        if child is None:
            def child(source, result):
                pathlib.Path(result).write_bytes(pathlib.Path(source).read_bytes())
        namespace["copy_in_child"] = child
        with patch.object(namespace["tempfile"], "mkdtemp", return_value=folder):
            namespace["Do"]("environment")
    return app.calls


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = self.temp.name

    def commands(self, app):
        return [call[1] for call in app.calls]

    def test_no_document_shows_error(self):
        app = FakeApp(with_document=False)
        run_probe(app, self.folder)
        self.assertEqual(["MsgBox"], self.commands(app))

    def test_declining_is_read_only(self):
        app = FakeApp(selection="normal", choice=0)
        run_probe(app, self.folder)
        self.assertEqual(["GetRasterSelectionRect", "MsgBox"], self.commands(app))
        self.assertIn("128 x 64", app.calls[1][2]["Text"])
        self.assertIn("Rect", app.calls[1][2]["Text"])

    def test_selected_roundtrip_saves_and_restores_selection(self):
        app = FakeApp(selection="normal")
        run_probe(app, self.folder)
        self.assertEqual([
            "GetRasterSelectionRect", "MsgBox", "SelectSaveDisk", "DuplicateWindow",
            "SelectNone", "ReturnImageInfo", "LayerMergeAll", "FileSaveAs", "FileOpen", "SelectAll", "NegativeImage",
            "Copy", "PasteAsNewLayer", "SelectLoadDisk", "MaskShowSelection", "MsgBox"
        ], self.commands(app))
        calls = {call[1]: call for call in app.calls}
        self.assertIs(app.TargetDocument, calls["SelectSaveDisk"][3])
        self.assertEqual("duplicate", calls["FileSaveAs"][3].Name)
        self.assertEqual("opened", calls["Copy"][3].Name)
        self.assertEqual("opened", calls["NegativeImage"][3].Name)
        self.assertIs(app.TargetDocument, calls["PasteAsNewLayer"][3])
        self.assertIs(app.TargetDocument, calls["MaskShowSelection"][3])
        self.assertEqual(calls["SelectSaveDisk"][2]["FileName"], calls["SelectLoadDisk"][2]["FileName"])
        self.assertFalse(calls["SelectSaveDisk"][2]["Overwrite"])
        self.assertIn(calls["SelectSaveDisk"][2]["FileName"], app.calls[-1][2]["Text"])
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "result.png")))
        self.assertIn('original document "original"', app.calls[-1][2]["Text"])

    def test_selected_runs_use_distinct_selection_names(self):
        names = []
        for _ in range(2):
            app = FakeApp(selection="normal")
            run_probe(app, self.folder)
            names.append(next(call[2]["FileName"] for call in app.calls
                              if call[1] == "SelectSaveDisk"))
        self.assertNotEqual(names[0], names[1])

    def test_selection_failures_report_stage_and_name(self):
        for command, stage in (("SelectSaveDisk", "saving selection"),
                               ("SelectLoadDisk", "restoring selection")):
            with self.subTest(command=command):
                app = FakeApp(selection="normal", fail_on=command)
                with self.assertRaisesRegex(RuntimeError, "Simulated host failure"):
                    run_probe(app, self.folder)
                name = next(call[2]["FileName"] for call in app.calls
                            if call[1] == "SelectSaveDisk")
                self.assertIn(stage, app.calls[-1][2]["Text"])
                self.assertIn(name, app.calls[-1][2]["Text"])
                self.assertNotIn("MaskShowSelection", self.commands(app))

    def test_no_selection_skips_selection_and_mask_commands(self):
        app = FakeApp()
        run_probe(app, self.folder)
        for command in ("SelectSaveDisk", "SelectLoadDisk", "MaskShowSelection"):
            self.assertNotIn(command, self.commands(app))

    def test_single_layer_does_not_attempt_merge(self):
        app = FakeApp(layers=1, fail_on="LayerMergeAll")
        run_probe(app, self.folder)
        self.assertIn("ReturnImageInfo", self.commands(app))
        self.assertIn("FileSaveAs", self.commands(app))
        self.assertIn("PasteAsNewLayer", self.commands(app))
        self.assertNotIn("LayerMergeAll", self.commands(app))

    def test_floating_selection_is_rejected(self):
        app = FakeApp(selection="floating")
        run_probe(app, self.folder)
        self.assertEqual(["GetRasterSelectionRect", "MsgBox", "MsgBox"], self.commands(app))
        self.assertIn("Floating", app.calls[-1][2]["Text"])

    def test_export_command_failures_identify_failing_command(self):
        for command in ("SelectNone", "ReturnImageInfo", "LayerMergeAll", "FileSaveAs"):
            with self.subTest(command=command):
                app = FakeApp(fail_on=command)
                with self.assertRaisesRegex(RuntimeError, "Simulated host failure"):
                    run_probe(app, self.folder)
                self.assertIn(command, app.calls[-1][2]["Text"])
                self.assertNotIn("PasteAsNewLayer", self.commands(app))

    def test_child_failure_is_reported_and_never_opens_result(self):
        app = FakeApp()
        def fail(source, result):
            raise RuntimeError("child failed")
        with self.assertRaisesRegex(RuntimeError, "child failed"):
            run_probe(app, self.folder, fail)
        self.assertIn("running external process", app.calls[-1][2]["Text"])
        self.assertNotIn("FileOpen", self.commands(app))

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell required")
    def test_external_process_copies_file_with_spaces(self):
        source = pathlib.Path(self.folder) / "source image.png"
        result = pathlib.Path(self.folder) / "result image.png"
        source.write_bytes(b"test image bytes")
        psp = types.ModuleType("PSPApp")
        psp.App = FakeApp()
        namespace = {}
        with patch.dict(sys.modules, {"PSPApp": psp}):
            exec(compile(SCRIPT.read_bytes(), str(SCRIPT), "exec"), namespace)
        namespace["copy_in_child"](str(source), str(result))
        self.assertEqual(source.read_bytes(), result.read_bytes())


if __name__ == "__main__":
    unittest.main()
