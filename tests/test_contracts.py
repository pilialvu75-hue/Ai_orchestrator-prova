import unittest

from airlab.contracts import BuildRequest


class BuildRequestTests(unittest.TestCase):
    def test_requires_task(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest.from_json({})

    def test_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            BuildRequest.from_json({"task": "build app", "mode": "magic"})

    def test_accepts_minimal_request(self) -> None:
        request = BuildRequest.from_json({"task": "build app"})
        self.assertEqual(request.mode, "plan")
        self.assertEqual(request.target, "web")


if __name__ == "__main__":
    unittest.main()
