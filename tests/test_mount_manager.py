"""Safety tests for removable-drive state detection and repair."""

import unittest
from unittest.mock import patch

import mount_manager


CFG = {
    "removable": True,
    "storage_path": "/media/pi/Tag_Node_1",
    "fs_type": "ntfs-3g",
    "fs_uuid": "test-uuid",
}


class MountManagerTests(unittest.TestCase):
    @patch.object(mount_manager, "IS_LINUX", True)
    @patch("mount_manager.resolve_device", return_value=None)
    def test_missing_expected_device_is_absent_even_if_mountpoint_exists(self, _resolve):
        self.assertEqual(mount_manager.classify(CFG), mount_manager.ABSENT)

    @patch.object(mount_manager, "IS_LINUX", True)
    @patch("mount_manager.is_mounted", return_value=False)
    @patch("mount_manager.resolve_device", return_value="/dev/sdz1")
    def test_present_but_not_mounted_is_repairable(self, _resolve, _mounted):
        self.assertEqual(mount_manager.classify(CFG), mount_manager.UNMOUNTED)

    @patch.object(mount_manager, "IS_LINUX", True)
    @patch("mount_manager.os.path.ismount", return_value=True)
    @patch("mount_manager.resolve_device", return_value="/dev/sdz1")
    @patch("mount_manager._run", return_value=(0, "/dev/sdy1", ""))
    def test_wrong_drive_at_mountpoint_is_not_healthy(self, _run, _resolve, _ismount):
        self.assertEqual(mount_manager.classify(CFG), mount_manager.UNMOUNTED)

    @patch.object(mount_manager, "IS_LINUX", True)
    @patch("mount_manager.classify", side_effect=[mount_manager.UNMOUNTED, mount_manager.MOUNTED])
    @patch("mount_manager._run", return_value=(0, "", ""))
    @patch("mount_manager._device_mount_targets", return_value=["/media/pi/old-Tag_Node_1"])
    @patch("mount_manager._device_is_mounted", return_value=True)
    @patch("mount_manager.resolve_device", return_value="/dev/sdz1")
    @patch("mount_manager.is_mounted", return_value=False)
    def test_repair_replaces_an_old_mount_instead_of_creating_a_copy(
        self, _mounted, _resolve, _in_use, _targets, run, _classify
    ):
        result = mount_manager.attempt_repair(CFG, logger=lambda _message: None)
        commands = [call.args[0] for call in run.call_args_list]

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertIn(["sudo", "-n", "umount", "/media/pi/old-Tag_Node_1"], commands)
        self.assertIn(["sudo", "-n", "mount", "-t", "ntfs-3g", "/dev/sdz1", CFG["storage_path"]], commands)
        self.assertFalse(any("ntfsfix" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
