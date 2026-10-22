import contextlib
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml.validate_dataset import validate_dataset


FIELDS = [
    "timestamp", "service", "request_rate", "error_ratio",
    "p95_latency_seconds",
]
SERVICES = ("user-service", "order-service", "payment-service")


def write_dataset(path, error_ratios=("0", "0", "0")):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for service, ratio in zip(SERVICES, error_ratios):
            writer.writerow({
                "timestamp": "2026-10-18T10:00:00+00:00",
                "service": service,
                "request_rate": "1.0",
                "error_ratio": ratio,
                "p95_latency_seconds": "0.1",
            })


class TestValidateDataset(unittest.TestCase):
    def test_constant_zero_error_ratio_warns_but_does_not_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            write_dataset(path)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                valid = validate_dataset(path)
        self.assertTrue(valid)
        self.assertIn("WARNING: error_ratio is zero in every row", output.getvalue())

    def test_nonzero_error_ratio_does_not_trigger_zero_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            write_dataset(path, ("0", "0.1", "0"))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                valid = validate_dataset(path)
        self.assertTrue(valid)
        self.assertNotIn("WARNING: error_ratio is zero in every row", output.getvalue())

    def test_default_dataset_path_respects_dataset_path_environment(self):
        # Validate the environment-aware default used by the CLI.
        import ml.validate_dataset as module
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            write_dataset(path)
            with patch.dict("os.environ", {"DATASET_PATH": str(path)}):
                # Reload so the module-level default follows the environment.
                import importlib
                reloaded = importlib.reload(module)
                self.assertEqual(reloaded.DATASET, path)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertTrue(reloaded.validate_dataset())
                importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
