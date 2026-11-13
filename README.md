# EasyCraftGen PaintShop Pro scripting probe

This folder contains an experimental EasyCraftGen integration and a separate
scripting probe for PaintShop Pro 2023; neither is an `.8bf` plug-in. The scripts use Python
2.7-compatible syntax and PaintShop Pro's scripting commands. An earlier
version successfully duplicated a layer and applied a negative effect in a
user test. In a subsequent user run, `composite.png` and `result.png` matched
on disk, and the opened result showed the unsaved negative effect, as intended.
After the single-layer merge fix, a user confirmed the original document
received a new layer with the modification. Alignment and selection-mask
behavior were confirmed for a rectangular selection. Feathering, integration
with actual generation, and selection-bound interpretation remain unverified
in the host.

## Run EasyCraftGen

1. Build or unpack the Windows EasyCraftGen application. A source build with
   `dotnet build EasyCraftGen.sln -c Release` produces an executable under
   `EasyCraftGen\bin\Release\net10.0`; keep it with the other build outputs.
   The source build requires the .NET runtime; a self-contained package does not.
   Start Easy Diffusion separately.
2. Copy `EasyCraftGen.PspScript` into
   `%USERPROFILE%\Documents\Corel PaintShop Pro\2023\Scripts-Trusted`.
   Edit that installed copy and set `EASYCRAFTGEN_EXE` at the top to the full
   path of `EasyCraftGen.exe`, keeping the `r'...'` quotes. Only install scripts
   you trust: trusted scripts can access files and launch programs.
3. Use **File > Script > Run** or bind **EasyCraftGen** to a toolbar as below.
   Start with a disposable RGB image and, for the first selected test, an
   off-center rectangle. The confirmation shows raw PSP selection data and the
   interpreted `(left, top, width, height)` generation bounds; verify them.
   PSP's nested rectangle uses an origin and dimensions. Fractional bounds
   are rounded outward to cover the selection.
4. Enter a prompt, select an appropriate Easy Diffusion model, and choose
   **Generate fill / edit**. On success the window closes and the script pastes
   the result as a new layer, masking it with the original selection when
   present. Without a selection it edits the whole image. The **Cancel** button
   cancels the current request locally; close the window to abandon the job.
   The server may continue processing a cancelled request.

PaintShop Pro may wait while the script is running. Do not edit or switch
documents until the operation completes. The script checks the original
document dimensions and selection before pasting, but cannot detect all
image changes or a selection shape change with identical bounds. Selection
bounds drive a rectangular generation mask; PSP's actual selection drives the
final mask. Optimized crops are restored to a full-size image for pasting.
Upscaling is not available in PaintShop Pro mode. Floating selections are
rejected.

The script replaces the clipboard and leaves the duplicate and result documents
open. It retains a temporary folder containing source and generated images;
the final dialog reports its location. It also retains a uniquely named
selection in PSP's configured selection location and reports that name. Delete
these specifically identified artifacts manually when no longer needed; image
files may contain private data. Multilayer export merges to a background and
may lose transparency. If the operation fails after pasting, inspect or undo
partial changes. This integration has automated mock tests, but has not yet
been exercised end-to-end inside PaintShop Pro.

## Install and run the probe

Copy `EasyCraftGen Probe.PspScript` to
`%USERPROFILE%\Documents\Corel PaintShop Pro\2023\Scripts-Trusted`,
replacing the earlier probe if present. Only put scripts you trust in this
folder; trusted scripts can access files and launch programs. In PaintShop
Pro's Edit workspace, run it with **File > Script > Run**, or bind it to a
toolbar or menu as described below.

Use a **disposable copy** of a small RGB document. The test replaces the
clipboard, creates files in a unique temporary directory, opens two additional
documents, and adds a layer and possibly a mask to the original. It does not
send anything to a server. Generated files may contain private image data;
the success or failure message gives their directory. Delete that specific
directory manually after inspecting it. Undo or discard changes and close the
two test documents without saving. Failures can leave partial changes.

1. Start with no selection and run the probe. The first dialog reports the
   raw selection information and asks for confirmation. **No** makes no
   edits; **Yes** runs the round trip. Floating selections are rejected.
2. The script duplicates the document, clears the selection on the duplicate,
   merges visible layers there if the duplicate has more than one layer, and
   exports `composite.png`. It starts Windows
   PowerShell to copy that file to `result.png` and verifies the copy. It
   then opens the result, applies Negative Image to that temporary document,
   and pastes it as a new layer in the original. This visible effect makes
   alignment and mask coverage easier to inspect.
   Compare the exported PNG to your visible composite, including any hidden
   layers, and check that the pasted layer is aligned. When merging, the
   flattening step creates a background layer, so this test does **not**
   establish transparency preservation.
3. Repeat with an off-center rectangular selection and with an irregular,
   feathered selection. The script saves the selection under a unique
   `EasyCraftGenProbe_...` name through PaintShop Pro's selection mechanism,
   reloads it after pasting, and uses
   `MaskShowSelection`. Check that the selection and layer mask match the
   original shape and feathering. Disable or move the mask/layer in the
   Layers palette if needed to inspect it. Compare the raw selection data
   in the dialog and report it, especially the bounding coordinates. The
   selection name is shown in the completion or error dialog. PaintShop Pro
   chooses its selection storage location, which may be one of the configured
   **File Locations > Selections** folders rather than the temporary directory.
   The probe does not remove this selection; delete the specifically named
   selection manually after testing if it is no longer needed.
4. Repeat with a multilayer document and compare the saved composite to what
   was visible. The duplicate and result documents remain open for
   inspection; the original is not flattened or saved by the probe.

The PowerShell child simply copies the file and normally finishes quickly:
the test establishes process launch and file exchange, **not** whether
PaintShop Pro stays responsive during a long generation. The saved
selection is PaintShop Pro's format, not a PNG diffusion mask. Exporting
the precise mask as a machine-readable grayscale image, positioning a
**cropped** result at an arbitrary offset, and handling asynchronous jobs or
document changes are still untested. This probe imports a full-size copy.
Precise alignment, selection restoration and mask behavior remain to be
verified in the real host; mocks only exercise control flow.

If a stage fails, the error dialog names the stage or command and temporary folder;
check the Script Output palette for details. Keep the error and raw selection
data when reporting results.

## Add a one-click toolbar or menu entry

1. Choose **View > Customize**, then open the **Scripts** tab.
2. Choose **EasyCraftGen** (or **EasyCraftGen Probe** for the test) from the script list, choose an icon, and
   click **Bind**.
3. Drag the new entry from **Bound Scripts** onto a toolbar or menu. Close
   the Customize dialog. A bound script can also be assigned a keyboard
   shortcut through the customization controls.

If the script isn't listed, verify the trusted folder and restart PaintShop
Pro. After editing the project copy, copy it into the trusted folder again.
See Corel's [binding instructions](https://help.corel.com/paintshop-pro/v21/en/official-help/Corel_PaintShop_Pro/Assigning_icons_to_scripts.html).

## Mock tests and references

Run `python -m unittest discover -s tests` with Python 3. The `.PspScript`
itself runs in PaintShop Pro's embedded Python and has not been validated by
these mocks against the host.

Corel references: [scripting basics](https://help.corel.com/paintshop-pro/v24/en/help/Corel_PaintShop_Pro/scripting_basics.html),
[selection API](https://product.corel.com/help/PaintShop-Pro/540214299/Main/EN/API/G/GetRasterSelectionRect.html),
[selection mask command](https://product.corel.com/help/PaintShop-Pro/540214299/Main/EN/API/M/MaskShowSelection.html),
and [merge visible layers to background](https://product.corel.com/help/PaintShop-Pro/540214299/Main/EN/API/L/LayerMergeAll.html).
