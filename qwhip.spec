# PyInstaller build recipe. Run `python build.py` rather than calling this directly.
#
# Builds two programs into ONE folder (dist/qwhip/) that share the same libraries:
#   qwhip.exe       the tray app (no console window)
#   qwhip-mcp.exe   the MCP server Claude starts (console program: it talks over stdin/stdout)

from PyInstaller.utils.hooks import copy_metadata

app = Analysis(["main.py"], pathex=["."])
mcp = Analysis(["mcp_server.py"], pathex=["."], datas=copy_metadata("mcp"))

app_exe = EXE(
    PYZ(app.pure), app.scripts, [],
    exclude_binaries=True, name="qwhip", icon="assets/qwhip.ico", console=False,
)
mcp_exe = EXE(
    PYZ(mcp.pure), mcp.scripts, [],
    exclude_binaries=True, name="qwhip-mcp", icon="assets/qwhip.ico", console=True,
)

COLLECT(
    app_exe, app.binaries, app.datas,
    mcp_exe, mcp.binaries, mcp.datas,
    name="qwhip",
)
