import os
import re
import shlex
import shutil
import subprocess


_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SIZE_PATTERN = re.compile(r"(?:Physical|Override) size:\s*(\d+)x(\d+)")
_KEY_CODES = {
    "ENTER": "KEYCODE_ENTER",
    "BACKSPACE": "KEYCODE_DEL",
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "TAB": "KEYCODE_TAB",
    "ESCAPE": "KEYCODE_ESCAPE",
    "SPACE": "KEYCODE_SPACE",
    "UP": "KEYCODE_DPAD_UP",
    "DOWN": "KEYCODE_DPAD_DOWN",
    "LEFT": "KEYCODE_DPAD_LEFT",
    "RIGHT": "KEYCODE_DPAD_RIGHT",
    "VOLUME_UP": "KEYCODE_VOLUME_UP",
    "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN",
}


class ADBError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def _adb_command(args, serial=None, timeout=10, binary=False):
    adb = os.environ.get("ADB_PATH") or shutil.which("adb")
    if not adb:
        raise ADBError(503, "ADB is not installed or is not available in PATH.")

    command = [adb]
    if serial:
        validate_serial(serial)
        command.extend(["-s", serial])
    command.extend(args)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ADBError(504, "The ADB command timed out.") from exc
    except OSError as exc:
        raise ADBError(503, f"Could not start ADB: {exc}") from exc

    stdout = result.stdout if binary else result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ADBError(502, stderr[:300] or "ADB command failed.")
    return stdout


def validate_serial(serial):
    if not _SERIAL_PATTERN.fullmatch(serial or ""):
        raise ADBError(400, "Invalid device serial.")
    return serial


def list_devices():
    output = _adb_command(["devices", "-l"])
    devices = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2:
            continue
        serial, state = fields[:2]
        if not _SERIAL_PATTERN.fullmatch(serial):
            continue
        metadata = dict(
            field.split(":", 1)
            for field in fields[2:]
            if ":" in field
        )
        devices.append({
            "serial": serial,
            "state": state,
            "model": metadata.get("model", "Android device").replace("_", " "),
            "product": metadata.get("product", ""),
            "device": metadata.get("device", ""),
        })
    return devices


def _require_connected_device(serial):
    validate_serial(serial)
    device = next((item for item in list_devices() if item["serial"] == serial), None)
    if not device:
        raise ADBError(404, "Device is not connected to this ADB host.")
    if device["state"] != "device":
        raise ADBError(409, f"Device is not ready (ADB state: {device['state']}).")
    return device


def get_device_info(serial):
    _require_connected_device(serial)
    size_output = _adb_command(["shell", "wm", "size"], serial=serial)
    sizes = _SIZE_PATTERN.findall(size_output)
    if not sizes:
        raise ADBError(502, "Could not read the device screen size.")
    width, height = (int(value) for value in sizes[-1])

    airplane_output = _adb_command(
        ["shell", "settings", "get", "global", "airplane_mode_on"],
        serial=serial,
    )
    airplane_mode = True if airplane_output == "1" else False if airplane_output == "0" else None
    return {"serial": serial, "width": width, "height": height, "airplane_mode": airplane_mode}


def capture_screen(serial):
    data = _adb_command(["exec-out", "screencap", "-p"], serial=serial, timeout=8, binary=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ADBError(502, "ADB returned an invalid screen frame.")
    return data


def wake_screen(serial):
    _require_connected_device(serial)
    _adb_command(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], serial=serial)


def set_airplane_mode(serial, enabled):
    _require_connected_device(serial)
    state = "enable" if enabled else "disable"
    _adb_command(["shell", "cmd", "connectivity", "airplane-mode", state], serial=serial)


def send_text(serial, text):
    if (
        not text
        or len(text) > 1000
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        raise ADBError(
            422,
            "Text must be 1-1000 characters and cannot contain control characters.",
        )
    if "%s" in text:
        raise ADBError(422, "The text sequence '%s' is reserved for spaces by Android input.")
    _require_connected_device(serial)
    encoded = shlex.quote(text.replace(" ", "%s"))
    _adb_command(["shell", f"input text {encoded}"], serial=serial)


def send_key(serial, key):
    key_code = _KEY_CODES.get((key or "").upper())
    if not key_code:
        raise ADBError(422, "Unsupported keyboard key.")
    _require_connected_device(serial)
    _adb_command(["shell", "input", "keyevent", key_code], serial=serial)


def tap_screen(serial, x, y):
    info = get_device_info(serial)
    px = min(info["width"] - 1, max(0, round(x * (info["width"] - 1))))
    py = min(info["height"] - 1, max(0, round(y * (info["height"] - 1))))
    _adb_command(["shell", "input", "tap", str(px), str(py)], serial=serial)
