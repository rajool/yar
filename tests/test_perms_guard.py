"""perms-guard: blocks force-recursive deletes and force container removal.

Exercises ``reason_for_segment`` (which unwraps a leading ``sudo`` and dispatches to
``rm_reason`` / ``docker_reason``) over whole command lines, covering each pattern
named in the script's deny policy plus the safe cases it must let through.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

pg = load("scripts/perms-guard.py", "perms_guard")


def decide(cmd):
    """Return perms-guard's block reason for a full command line, or None to allow."""
    for seg in pg.split_segments(cmd):
        if not seg.strip():
            continue
        reason = pg.reason_for_segment(seg)
        if reason:
            return reason
    return None


class BlocksForceRecursiveDelete(unittest.TestCase):
    def test_rm_rf_variants(self):
        for cmd in ("rm -rf x", "rm -fr x", "rm -Rf x", "rm -r -f x",
                    "rm -f -r x", "rm --recursive --force x"):
            self.assertIsNotNone(decide(cmd), cmd)

    def test_sudo_is_unwrapped(self):
        self.assertIsNotNone(decide("sudo rm -rf /x"))
        self.assertIsNotNone(decide("sudo -u root rm -rf /x"))  # value-taking opt skipped

    def test_inside_compound_command(self):
        self.assertIsNotNone(decide("cd /tmp && rm -rf build"))


class BlocksDockerForceRemove(unittest.TestCase):
    def test_docker_rm_force(self):
        for cmd in ("docker rm -f c", "docker rm --force c", "docker rm -vf c"):
            self.assertIsNotNone(decide(cmd), cmd)

    def test_docker_container_rm_force(self):
        self.assertIsNotNone(decide("docker container rm -f c"))

    def test_docker_global_options_skipped(self):
        self.assertIsNotNone(decide("docker -H tcp://x rm -f c"))


class AllowsSafeCommands(unittest.TestCase):
    def test_rm_without_both_flags(self):
        for cmd in ("rm -f x", "rm -r x", "rm x", "rm -i x"):
            self.assertIsNone(decide(cmd), cmd)

    def test_double_dash_ends_options(self):
        # `rm -- -rf` deletes a file literally named "-rf"; not recursive+force.
        self.assertIsNone(decide("rm -- -rf"))

    def test_docker_without_force(self):
        for cmd in ("docker rm c", "docker container rm c", "docker ps"):
            self.assertIsNone(decide(cmd), cmd)

    def test_unrelated_commands(self):
        for cmd in ("echo rm -rf x", "ls -rf", "grep -rf pattern ."):
            self.assertIsNone(decide(cmd), cmd)


if __name__ == "__main__":
    unittest.main()
