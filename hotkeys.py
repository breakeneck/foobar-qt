"""Remappable keyboard control.

Local shortcuts are window-wide QShortcuts rebuilt whenever the mapping
changes. Escape is the exception: while the search field holds text it must
clear the search instead of minimizing, and window-wide QShortcuts win over
the focused QLineEdit, so Escape is routed through FooQt.keyPressEvent.

Global shortcuts use KDE's KGlobalAccel (embedded in KWin on Plasma 6) over
D-Bus:

  * method calls with array-typed arguments (as/ai) are marshalled by the
    gdbus CLI, because PyQt6's QtDBus can only send QVariant lists (av),
    which KWin rejects;
  * globalShortcutPressed is received through plain QtDBus signal matching.
    The sender filter stays empty on purpose: KWin emits from its unique
    bus name, not from org.kde.kglobalaccel; the component is filtered in
    the handler instead.

On non-KDE desktops (or without gdbus) the global backend reports itself
unavailable and the global column of the Hotkeys dialog is disabled.
"""

import shutil
import subprocess

from PyQt6 import QtCore, QtGui

try:
    from PyQt6.QtDBus import QDBusConnection, QDBusInterface
except ImportError:  # pragma: no cover - QtDBus ships with PyQt6-Qt6
    QDBusConnection = QDBusInterface = None

# (action id, user-visible label, default in-app shortcut)
ACTIONS = [
    ("play_pause", "Play / Pause", "Space"),
    ("next", "Next Track", "Ctrl+Down"),
    ("prev", "Previous Track", "Ctrl+Up"),
    ("minimize", "Minimize App", "Escape"),
    ("search", "Focus Search", "F3"),
    ("skip_track", "Skip Track (toggle)", "Ctrl+S"),
]

# handled in FooQt.keyPressEvent, see the module docstring
ESCAPE = "Escape"


def defaults():
    return {aid: {"local": default, "global": ""} for aid, _label, default in ACTIONS}


def normalize(stored):
    """Merge a stored mapping into a complete defaults-shaped dict."""
    result = defaults()
    for aid, entry in (stored or {}).items():
        if aid not in result or not isinstance(entry, dict):
            continue
        result[aid] = {
            "local": entry.get("local", result[aid]["local"]),
            "global": entry.get("global", ""),
        }
    return result


def _gvar_str(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')


def _gvar_list(items):
    return "[" + ",".join(_gvar_str(i) for i in items) + "]"


class KdeBackend(QtCore.QObject):
    SERVICE = "org.kde.kglobalaccel"
    INTERFACE = "org.kde.KGlobalAccel"
    PATH = "/kglobalaccel"
    COMPONENT_INTERFACE = "org.kde.kglobalaccel.Component"
    COMPONENT = "org.fooqt.player"
    FRIENDLY = "FooQt"
    # kglobalaccel's SetPresent flag: the app is running, keep the grab
    SET_PRESENT = 2

    pressed = QtCore.pyqtSignal(str)  # action id

    class RegistrationError(Exception):
        pass

    def __init__(self, parent=None):
        super().__init__(parent)
        self._component_path = ""
        self._listening = False

    def available(self):
        if QDBusConnection is None or shutil.which("gdbus") is None:
            return False
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected() or bus.interface() is None:
            return False
        reply = bus.interface().isServiceRegistered(self.SERVICE)
        # isServiceRegistered can come back as a QDBusReply wrapper
        if hasattr(reply, "isValid"):
            return reply.isValid() and bool(reply.value())
        return bool(reply)

    def _gdbus(self, method, *args):
        cmd = [
            "gdbus",
            "call",
            "--session",
            "--dest",
            self.SERVICE,
            "--object-path",
            self.PATH,
            "--method",
            "%s.%s" % (self.INTERFACE, method),
            *args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise self.RegistrationError(
                result.stderr.strip() or "gdbus call %s failed" % method
            )
        return result.stdout.strip()

    def register(self, action_id, label, seq_str):
        """Grab seq_str system-wide. Returns (ok, message)."""
        if not self.available():
            return False, "global hotkeys unavailable (KDE session required)"

        sequence = QtGui.QKeySequence(seq_str)
        if sequence.isEmpty():
            # cleared: drop any previous grab
            self.unregister(action_id)
            return True, ""

        combined = int(sequence[0].toCombined())
        if combined <= 0:
            return False, "invalid key sequence"

        action = _gvar_list([self.COMPONENT, action_id, self.FRIENDLY, label])
        try:
            self._gdbus("doRegister", action)
            reply = self._gdbus(
                "setShortcut", action, "[%d]" % combined, "uint32 %d" % self.SET_PRESENT
            )
        except (self.RegistrationError, OSError, subprocess.TimeoutExpired) as e:
            return False, str(e)

        # setShortcut replies with the keys it actually grabbed; an empty
        # reply means the shortcut was rejected (usually a conflict)
        if str(combined) not in reply:
            return False, "rejected (conflict with another shortcut?)"

        self._ensure_component()
        return True, ""

    def unregister(self, action_id):
        if not self.available():
            return
        try:
            self._gdbus("unregister", self.COMPONENT, action_id)
        except (self.RegistrationError, OSError, subprocess.TimeoutExpired) as e:
            print("global shortcut unregister failed: %s" % e)

    def _ensure_component(self):
        if self._listening or QDBusConnection is None:
            return
        bus = QDBusConnection.sessionBus()
        iface = QDBusInterface(self.SERVICE, self.PATH, self.INTERFACE, bus)
        reply = iface.call("getComponent", self.COMPONENT)
        if not reply.arguments():
            return
        path = reply.arguments()[0]
        path = path.path() if hasattr(path, "path") else str(path)
        # empty service: no sender match rule, see the module docstring
        if bus.connect(
            "", path, self.COMPONENT_INTERFACE, "globalShortcutPressed", self._onPressed
        ):
            self._component_path = path
            self._listening = True

    @QtCore.pyqtSlot(str, str, "qlonglong")
    def _onPressed(self, component, action, timestamp):
        if component == self.COMPONENT:
            self.pressed.emit(action)


class HotkeyManager(QtCore.QObject):
    """Owns the current mapping and turns it into live grabs."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.labels = {aid: label for aid, label, _default in ACTIONS}
        self.mapping = defaults()
        self._shortcuts = {}
        self.globalAccel = KdeBackend(self)
        self.globalAccel.pressed.connect(self.dispatch)

    def localFor(self, action_id):
        return self.mapping.get(action_id, {}).get("local", "")

    def apply(self, mapping):
        """(Re)build local QShortcuts and global grabs. Returns a list of
        (label, sequence, message) for global registrations that failed."""
        self.mapping = normalize(mapping)

        for shortcut in self._shortcuts.values():
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()

        for aid, _label, _default in ACTIONS:
            seq_str = self.mapping[aid]["local"]
            if not seq_str or seq_str == ESCAPE:
                continue
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(seq_str), self.w)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(
                lambda checked=False, a=aid: self.dispatch(a)
            )
            self._shortcuts[aid] = shortcut

        report = []
        if self.globalAccel.available():
            for aid, label, _default in ACTIONS:
                global_seq = self.mapping[aid]["global"]
                if global_seq:
                    ok, message = self.globalAccel.register(aid, label, global_seq)
                    if not ok:
                        report.append((label, global_seq, message))
                else:
                    self.globalAccel.unregister(aid)
        return report

    def shutdown(self):
        """Drop all global grabs (the session keeps them otherwise)."""
        for aid, _label, _default in ACTIONS:
            self.globalAccel.unregister(aid)

    def dispatch(self, action_id):
        self.w.onHotkey(action_id)