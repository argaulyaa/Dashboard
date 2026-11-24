import unittest
from unittest.mock import patch

import mobile_devices


class MobileDevicesTests(unittest.TestCase):
    def test_list_devices_includes_states_and_model_names(self):
        output = (
            "List of devices attached\n"
            "R58N123456A device product:foo model:Pixel_8 device:foo\n"
            "emulator-5554 offline product:sdk model:Android_SDK device:emu\n"
        )
        with patch.object(mobile_devices, "_adb_command", return_value=output):
            devices = mobile_devices.list_devices()

        self.assertEqual(
            devices,
            [
                {
                    "serial": "R58N123456A",
                    "state": "device",
                    "model": "Pixel 8",
                    "product": "foo",
                    "device": "foo",
                },
                {
                    "serial": "emulator-5554",
                    "state": "offline",
                    "model": "Android SDK",
                    "product": "sdk",
                    "device": "emu",
                },
            ],
        )

    def test_input_text_quotes_shell_metacharacters(self):
        with (
            patch.object(mobile_devices, "_require_connected_device"),
            patch.object(mobile_devices, "_adb_command") as run_adb,
        ):
            mobile_devices.send_text("device-1", "hello; reboot now!")

        run_adb.assert_called_once_with(
            ["shell", "input text 'hello;%sreboot%snow!'"],
            serial="device-1",
        )

    def test_input_text_rejects_android_space_escape_sequence(self):
        with patch.object(mobile_devices, "_adb_command") as run_adb:
            with self.assertRaises(mobile_devices.ADBError) as raised:
                mobile_devices.send_text("device-1", "literal %s")

        self.assertEqual(raised.exception.status_code, 422)
        run_adb.assert_not_called()

    def test_input_text_rejects_control_characters(self):
        with patch.object(mobile_devices, "_adb_command") as run_adb:
            with self.assertRaises(mobile_devices.ADBError) as raised:
                mobile_devices.send_text("device-1", "hello\nworld")

        self.assertEqual(raised.exception.status_code, 422)
        run_adb.assert_not_called()

    def test_device_serial_rejects_command_fragments(self):
        with self.assertRaises(mobile_devices.ADBError) as raised:
            mobile_devices.validate_serial("device; reboot")

        self.assertEqual(raised.exception.status_code, 400)

    def test_airplane_mode_uses_only_the_requested_fixed_state(self):
        with (
            patch.object(mobile_devices, "_require_connected_device"),
            patch.object(mobile_devices, "_adb_command") as run_adb,
        ):
            mobile_devices.set_airplane_mode("device-1", True)

        run_adb.assert_called_once_with(
            ["shell", "cmd", "connectivity", "airplane-mode", "enable"],
            serial="device-1",
        )

    def test_tap_normalizes_coordinates_to_device_pixels(self):
        with (
            patch.object(
                mobile_devices,
                "get_device_info",
                return_value={"width": 1080, "height": 2400},
            ),
            patch.object(mobile_devices, "_adb_command") as run_adb,
        ):
            mobile_devices.tap_screen("device-1", 1, 0.5)

        run_adb.assert_called_once_with(
            ["shell", "input", "tap", "1079", "1200"],
            serial="device-1",
        )


if __name__ == "__main__":
    unittest.main()
