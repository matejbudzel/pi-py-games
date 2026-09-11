import unittest


class DancePackageTests(unittest.TestCase):
    def test_provider_package_imports_without_legacy_namespace(self):
        from games.dance import app

        self.assertIsNotNone(app.App)
