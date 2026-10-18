"""The test settings create a private document directory; it must not outlive the process that created it, and must never be touched by anyone else."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

BACKEND = Path(__file__).resolve().parents[2]
PREFIX = "talim-test-private-"
SETTINGS_PROBE = "from django.conf import settings; print(settings.PRIVATE_MEDIA_ROOT, flush=True)"


class PrivateTestDirectoryCleanup(SimpleTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def process(self, code, **kw):
        env = {**os.environ, "TMPDIR": str(self.tmp), "DJANGO_SETTINGS_MODULE": "config.settings.test"}
        return subprocess.Popen([sys.executable, "-c", code], cwd=str(BACKEND), env={**env, "PYTHONPATH": str(BACKEND)},
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, text=True, **kw)

    def run_to_end(self, code):
        p = self.process(code)
        out, err = p.communicate(timeout=120)
        return p.returncode, out, err

    def run_ok(self, code):
        rc, out, err = self.run_to_end(code)
        self.assertEqual(rc, 0, err)
        return out

    def leftovers(self):
        return sorted(p.name for p in self.tmp.iterdir() if p.name.startswith(PREFIX))

    def test_the_directory_exists_while_the_process_runs_and_is_gone_after_a_normal_exit(self):
        code, out, err = self.run_to_end(SETTINGS_PROBE + "; import os; assert os.path.isdir(settings.PRIVATE_MEDIA_ROOT)")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith(str(self.tmp)), out)
        self.assertEqual(self.leftovers(), [])

    def test_the_directory_is_removed_with_its_content_after_an_exception(self):
        code, _out, err = self.run_to_end(
            SETTINGS_PROBE + "; (settings.PRIVATE_MEDIA_ROOT / 'a').mkdir(); (settings.PRIVATE_MEDIA_ROOT / 'a' / 'f.bin').write_bytes(b'x'); raise RuntimeError('test failed')")
        self.assertNotEqual(code, 0)
        self.assertIn("RuntimeError: test failed", err)                  # it failed for the intended reason, not because the probe could not start
        self.assertEqual(self.leftovers(), [])

    def test_repeated_runs_do_not_accumulate_directories(self):
        for _ in range(3):
            self.run_ok(SETTINGS_PROBE)
        self.assertEqual(self.leftovers(), [])

    def test_only_its_own_directory_is_removed(self):
        stranger = self.tmp / (PREFIX + "belongs-to-someone-else")      # same prefix, created by another (still running) process
        stranger.mkdir()
        (stranger / "keep.txt").write_text("keep")
        unrelated = self.tmp / "unrelated"
        unrelated.mkdir()
        self.run_ok(SETTINGS_PROBE)
        self.assertTrue((stranger / "keep.txt").exists())
        self.assertTrue(unrelated.is_dir())

    def test_a_finished_process_does_not_remove_the_directory_of_a_running_one(self):
        running = self.process(SETTINGS_PROBE + "; import sys; sys.stdin.readline()")
        try:
            path = Path(running.stdout.readline().strip())
            self.assertTrue(path.is_dir())
            self.run_ok(SETTINGS_PROBE)                                  # a second, independent process starts and finishes meanwhile
            self.assertTrue(path.is_dir(), "a concurrent process removed a directory it did not create")
        finally:
            running.communicate("\n", timeout=60)
        self.assertEqual(self.leftovers(), [])

    def test_a_forked_child_never_removes_the_directory_of_its_parent(self):
        code, out, err = self.run_to_end(
            SETTINGS_PROBE + "; import os, sys\n"
            "pid = os.fork()\n"
            "if pid == 0:\n    sys.exit(0)\n"                          # a normal interpreter exit in the child runs the inherited exit handlers
            "os.waitpid(pid, 0)\n"
            "print('alive' if os.path.isdir(settings.PRIVATE_MEDIA_ROOT) else 'GONE')")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.strip().endswith("alive"), out)
        self.assertEqual(self.leftovers(), [])
