import unittest, importlib
MODS = ["certpath_roadmap_studio.ui_server", ]


class TestOriginGuard(unittest.TestCase):
    def test_local_origins_allowed(self):
        for name in MODS:
            m = importlib.import_module(name)
            for o in (None, "", "http://localhost:8080", "http://127.0.0.1:9000", "https://localhost"):
                self.assertTrue(m._is_local_origin(o), (name, o))

    def test_foreign_origins_blocked(self):
        for name in MODS:
            m = importlib.import_module(name)
            for o in ("https://evil.example", "http://localhost.evil.example", "null", "file://", "http://192.168.1.5"):
                self.assertFalse(m._is_local_origin(o), (name, o))


if __name__ == "__main__":
    unittest.main()
