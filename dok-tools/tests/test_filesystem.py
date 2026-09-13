import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.filesystem import file_info, list_directory, read_file, search_files


class FilesystemToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "subdir").mkdir()
        (self.root / "hello.txt").write_text("Olá DOK\nOpenRouter aqui\n", encoding="utf-8")
        (self.root / "subdir" / "config.yaml").write_text("provider: openrouter\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _roots(self):
        return [self.root]

    def test_list_directory(self):
        with patch("tools.filesystem._allowed_roots", self._roots):
            result = list_directory(".")
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["entries"][0]["name"], "subdir")

    def test_read_file(self):
        with patch("tools.filesystem._allowed_roots", self._roots):
            result = read_file("hello.txt")
        self.assertIn("OpenRouter", result["content"])
        self.assertFalse(result["truncated"])

    def test_search_by_text_and_pattern(self):
        with patch("tools.filesystem._allowed_roots", self._roots):
            result = search_files(".", query="openrouter", pattern="*.txt")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["matches"][0]["name"], "hello.txt")

    def test_file_info(self):
        with patch("tools.filesystem._allowed_roots", self._roots):
            result = file_info("hello.txt")
        self.assertEqual(result["type"], "file")
        self.assertGreater(result["size_bytes"], 0)

    def test_path_escape_is_blocked(self):
        outside = self.root.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            with patch("tools.filesystem._allowed_roots", self._roots):
                with self.assertRaises(PermissionError):
                    read_file("../outside.txt")
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
