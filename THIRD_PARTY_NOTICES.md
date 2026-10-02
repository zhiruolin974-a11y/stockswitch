# Third-party software in Windows distributions

StockSwitch is a research and virtual-funds paper-trading application. A Windows
distribution bundles Python runtime components and open-source dependencies.
This notice is included in the portable and installed program directory.

- **Python 3.12 runtime**: Python Software Foundation License Version 2,
  including the bundled components and notices described in the
  [official Python license](https://docs.python.org/3.12/license.html).
- **PySide6 / Qt for Python, Qt libraries, Shiboken**: the installed community
  wheel identifies LGPL-3.0-only, GPL-2.0-only or GPL-3.0-only terms for
  PySide6. This product uses dynamically linked Qt libraries. See the
  [official Qt 6.11 module license inventory](https://doc.qt.io/qt-6.11/licensing.html),
  [LGPL obligations](https://doc.qt.io/qt-6.11/lgpl.html), and
  [third-party license inventory](https://doc.qt.io/qt-6.11/licenses-used-in-qt.html).
  Before public distribution, include the LGPLv3/GPLv3 full texts, applicable
  third-party notices and a workable way to replace compatible shared Qt
  libraries. The installed wheel's commercial-license reference is **not** a
  substitute for those open-source license texts.
- **tzdata**: Apache-2.0, as reported by the installed wheel metadata. Include
  its bundled license notice when distributing the wheel content.
- **PyInstaller bootloader**: the [PyInstaller license](https://pyinstaller.org/en/stable/license.html)
  states that generated bundles need no PyInstaller license or credit.

This file is an inventory, not a legal determination. **Do not publish the
current binary distribution** until the exact bundled files, full required
license texts, replacement procedure and their obligations have been reviewed.
