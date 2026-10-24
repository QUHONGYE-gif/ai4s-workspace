"""Keep one native PyMOL session behind the workbench's two display modes.

This file runs inside PyMOL, where Qt widgets and the command feedback live.
All RPC callbacks dispatch to the GUI thread before touching either one.
"""

from pymol import cmd, rpc
from pymol.Qt import QtGui, QtWidgets
from pmg_qt import pymol_qt_gui


class WorkspaceInterface:
    settings = ("internal_gui", "internal_feedback", "seq_view", "movie_panel", "text")

    def __init__(self):
        self.window = pymol_qt_gui.window
        self.full_ui = True
        self.saved_settings = {}
        self.saved_widgets = []
        self.set_mode(False)

    def set_mode(self, full_ui):
        if full_ui != self.full_ui:
            if full_ui:
                for name, value in self.saved_settings.items():
                    cmd.set(name, value)
                for widget in self.saved_widgets:
                    widget.show()
            else:
                self.saved_settings = {
                    name: cmd.get_setting_int(name) for name in self.settings
                }
                widgets = [self.window.menuBar()]
                widgets += self.window.findChildren(QtWidgets.QDockWidget)
                widgets += self.window.findChildren(QtWidgets.QToolBar)
                self.saved_widgets = [widget for widget in widgets if widget.isVisible()]
                for widget in self.saved_widgets:
                    widget.hide()
                for name in self.settings:
                    cmd.set(name, 0)
            self.full_ui = full_ui

        # Full-screen Qt covers the Linux panel without cropping native dialogs.
        self.window.showFullScreen()
        self.window.raise_()
        return {"full_ui": self.full_ui}

    def execute(self, command):
        # Flush earlier messages first, so each reply belongs to this command.
        self.window.update_feedback()
        document = self.window.browser.document()
        start = document.characterCount() - 1
        error = None
        try:
            cmd.do(command, log=1, echo=1, flush=1)
        except Exception as exception:
            error = str(exception)
        self.window.update_feedback()
        cursor = QtGui.QTextCursor(document)
        cursor.setPosition(min(start, document.characterCount() - 1))
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        output = cursor.selectedText()
        for separator in ("\u2028", "\u2029"):
            output = output.replace(separator, "\n")
        output = output.replace("\u00a0", " ").strip()
        if error:
            output = "\n".join(part for part in (output, error) if part)
        return {"output": output}


interface = cmd._call_in_gui_thread(WorkspaceInterface)
rpc.serv.register_function(
    lambda full_ui: cmd._call_in_gui_thread(lambda: interface.set_mode(full_ui)),
    "webSetMode",
)
rpc.serv.register_function(
    lambda command: cmd._call_in_gui_thread(lambda: interface.execute(command)),
    "webExecute",
)
rpc.serv.register_function(lambda: {"full_ui": interface.full_ui}, "webGetMode")
