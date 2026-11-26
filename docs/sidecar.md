# optdoc as a standalone program

For an application that ships optdoc beside it rather than inside it (medorello, as a Tauri
sidecar): one program with everything in it, Python, PyMuPDF, OpenCV, ONNX Runtime, RapidOCR with
its models, pillow-heif, Camelot with pandas and pdfium for the tables, PySide6 (Qt Widgets) for
the window. It needs no Python on the computer, loads nothing at run time and never goes on the
network. The application talks to it through the command line described in
[interface.md](interface.md).

## Build

On the computer the program is for (PyInstaller does not cross-build), from a checkout of the tag
the application pins:

```
uv sync --extra ocr --extra tables --extra gui --extra barcodes --group build
uv run python packaging/build.py
```

This writes into `dist/`:

| file | what it is |
|---|---|
| `optdoc-<target>` | the program; `<target>` is the Rust target triple Tauri expects, `aarch64-apple-darwin` on a Mac with Apple silicon |
| `optdoc-<target>.sha256` | its checksum |
| `optdoc-<target>.licences.json` | the packages inside, with versions and licences |

and then tries the program out the way an application uses it: `readers`; `prepare` on an
invented photographed laboratory report (its table must be found) with the temporary, home and
cache folders pointed at empty folders (they must stay empty); `prepare --config` with the
configuration it wrote (the same four files, byte for byte); `edit --self-test`, which goes
through the window without a person, off screen (the same files again, nothing left behind); a
failure (it must answer with its kind); on macOS `prepare` and the window once more with the
network closed by the system (`sandbox-exec`). It ends with a summary: size, checksum, timings,
checks. `--no-check` builds only.

Built on macOS 27 (Apple M1 Max) with optdoc 0.4.0, Python 3.13, PyInstaller 6.22:

| | one file (default) | folder (`--onedir`) |
|---|---|---|
| size | 162 MB | 506 MB |
| `optdoc readers` | 3.7 s | 0.25 s |
| `optdoc prepare` on a photographed one-page report | 13.9 s | 4.6 s |
| the same with `--no-cells` (no tables) | 9.7 s | 3.9 s |
| `optdoc edit --self-test` on it (window open to closed, without a person) | 16.2 s | 5.5 s |

Times are the mean of three runs; the first run after building or copying the program, or after a
while unused, takes longer (up to 27 s as one file). The one file unpacks itself into the temporary folder at every start (and
removes that copy at exit); that is where the difference goes. The folder starts at once. Both
pass the same checks.

## Into a Tauri application

**One file** (what Tauri calls a sidecar): put `optdoc-aarch64-apple-darwin` into
`src-tauri/binaries/` and name it in `tauri.conf.json`:

```json
{ "bundle": { "externalBin": ["binaries/optdoc"] } }
```

Tauri copies the file for the target it builds for into the application, beside its own
program. Start it with the shell plugin's `Command.sidecar("binaries/optdoc")` or from Rust.

**Folder**, for the shorter wait: put the folder `optdoc-aarch64-apple-darwin-onedir/` into the
application's resources (`bundle.resources`) and start
`<resources>/optdoc-aarch64-apple-darwin-onedir/optdoc` from Rust with `std::process::Command`. Every library in it has to be signed for notarisation;
the build signs them all when given an identity (below).

Either way: give `prepare` and `edit` an empty folder of its own for `--out`, read the answer from
standard output (always one JSON object; status 0 or 2), and with `--progress` read standard error
line by line for `{"page": n, "of": m}`. `edit` returns when the person closes the window, which may
take as long as they work: give it no time limit, and treat the error `cancelled` as no error. The
window asks to be brought to the front when it opens; whether macOS lets it come forward when another
application starts it has not been tried yet. With one file it appears after the unpacking, some
seconds after the start (the folder is quicker).

Tauri signs an `externalBin` again when it bundles the application, by default with the hardened
runtime (`bundle.macOS.hardenedRuntime`) and without optdoc's entitlements. The one file then does
not start: the system refuses the Python library it unpacks ("different Team IDs"). Either bundle
without the hardened runtime, or sign the program again after Tauri, with the hardened runtime and
`packaging/entitlements.plist`.

## Signing and notarising (macOS)

Without an identity the build is signed ad hoc, which is enough on the computer it was built on
and for trying out. For other computers:

```
uv run python packaging/build.py --identity "Developer ID Application: <name> (<team>)"
```

signs every library and the program with the hardened runtime and
`packaging/entitlements.plist` (`disable-library-validation`, because the one file loads the
libraries it has just unpacked). Inside an application, Tauri's notarisation of the application
covers the program. Notarised on its own: `ditto -c -k dist/optdoc-aarch64-apple-darwin
optdoc.zip`, then `xcrun notarytool submit optdoc.zip --wait …`. Not tried yet: there was no
Developer ID to try it with.

## Other systems

`packaging/build.py` names the program for Linux (`x86_64-unknown-linux-gnu`, …) and Windows
(`x86_64-pc-windows-msvc`, with `.exe`) as well, and the specification is not tied to macOS; built
and tried so far only on macOS.

## Licences

optdoc is AGPL-3.0-or-later, and so is PyMuPDF. The program carries further packages under
permissive licences (`optdoc-<target>.licences.json` lists them) and native libraries with their
own: OpenCV brings FFmpeg (LGPL), pillow-heif brings libheif and libde265 (LGPL) and x265 (GPL 2.0
or later), pypdfium2 brings pdfium (Apache 2.0 and BSD), PySide6 brings Qt (LGPL 3.0; its libraries
are loaded from the program's own files and can be replaced). An application that ships the program names optdoc, its licence and where its source
is (https://github.com/fre-ms/optdoc, the tag it pins).
