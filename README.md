DBI Backend (macOS GUI)
=======================

A PC-side server for installing Nintendo Switch titles over USB with
[DBI](https://github.com/rashevskyv/dbi) — now with a simple **macOS app** so you
don't need the Terminal, Homebrew, or Python.

This is a friendly fork of [lunixoid/dbibackend](https://github.com/lunixoid/dbibackend)
that adds:

- 🖥️ A native desktop GUI (folder picker, Start/Stop, live progress + log)
- 📦 A self-contained `DBI Backend.app` with **libusb bundled inside** — download and run
- 🍎 macOS fixes (no more `[Errno 19] No such device` from `dev.reset()`, no `DYLD` fiddling)
- 🔁 Auto-reconnect between installs

<br>

Download & run (easiest)
------------------------

1. Grab **`DBI-Backend-macOS-arm64.zip`** from the [Releases](../../releases) page and unzip it.
2. Because the app isn't code-signed, macOS Gatekeeper will block the first launch.
   **Right-click the app ▸ Open ▸ Open**, or run once in Terminal:
   ```bash
   xattr -dr com.apple.quarantine "DBI Backend.app"
   ```
3. Click **Choose…**, pick a folder containing your `.nsp` / `.nsz` / `.xci` files, and press **Start server**.
4. On the Switch: open **DBI ▸ Install title from USB**. Your titles appear — install the base game first, then any updates/DLC.

> Apple Silicon (M1/M2/M3+). Intel Macs should build from source (below).

<br>

Run from source
----------------

Requirements: Python 3.7+, [libusb](https://libusb.info) (`brew install libusb`).

```bash
git clone https://github.com/YahyaHammoudeh0/dbibackend.git
cd dbibackend
python3 -m venv .venv
.venv/bin/pip install pyusb==1.1.0

# GUI:
.venv/bin/python dbigui.py

# or command line:
.venv/bin/python dbibackend/dbibackend.py /path/to/titles_dir
```

<br>

Build the app yourself
----------------------

```bash
./build_macos.sh          # produces dist/DBI Backend.app
```

Pushing a `v*` tag builds and attaches the zipped app to a GitHub Release
automatically (see `.github/workflows/release.yml`).

<br>

Requirements on the Switch
--------------------------

- DBI **v202+** (newer is better)

<br>

Credits
-------

- Original `dbibackend` by **Kalashnikov Roman** ([lunixoid](https://github.com/lunixoid/dbibackend))
- DBI by [rashevskyv](https://github.com/rashevskyv/dbi)
- GUI + macOS packaging by [YahyaHammoudeh0](https://github.com/YahyaHammoudeh0)

MIT licensed — see [LICENSE](LICENSE).
