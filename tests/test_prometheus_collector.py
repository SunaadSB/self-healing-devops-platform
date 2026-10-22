
import unittest
from unittest.mock import patch

from ml.prometheus_collector import (
    PrometheusError,
    _calculate_error_ratios,
    _series_by_service,
    collect_features,
)


def sample(service, value):
    return {
        "metric": {"service": service},
        "value": [123.0, str(value)],
    }


class TestPrometheusCollector(unittest.TestCase):

    def test_series_are_mapped_by_service(self):
        result = _series_by_service([
            sample("user-service", 0.25),
            sample("order-service", 0.50),
        ])
        self.assertEqual(result["user-service"], 0.25)
        self.assertEqual(result["order-service"], 0.50)

    def test_job_labels_are_mapped_to_canonical_service_names(self):
        result = _series_by_service([
            {
                "metric": {"job": "ai-self-healing-user-service"},
                "value": [0, "0.25"],
            },
            {
                "metric": {"job": "ai-self-healing-order-service"},
                "value": [0, "0.50"],
            },
            {
                "metric": {"job": "unrelated-job"},
                "value": [0, "0.75"],
            },
        ])
        self.assertEqual(result["user-service"], 0.25)
        self.assertEqual(result["order-service"], 0.50)
        self.assertNotIn("payment-service", result)

    def test_invalid_values_are_ignored(self):
        self.assertEqual(
            _series_by_service([
                sample("user-service", "NaN"),
                sample("unknown-service", 0.25),
            ]),
            {},
        )

    def test_error_ratio_is_calculated(self):
        ratios = _calculate_error_ratios(
            {"user-service": 10.0},
            {"user-service": 2.0},
        )
        self.assertEqual(ratios["user-service"], 0.2)

    def test_missing_error_series_is_unknown_not_zero(self):
        ratios = _calculate_error_ratios(
            {"user-service": 10.0},
            {},
        )
        self.assertIsNone(ratios["user-service"])

    def test_explicit_zero_error_rate_means_zero_errors(self):
        ratios = _calculate_error_ratios(
            {"user-service": 10.0},
            {"user-service": 0.0},
        )
        self.assertEqual(ratios["user-service"], 0.0)

    def test_missing_error_series_does_not_hide_other_service_data(self):
        ratios = _calculate_error_ratios(
            {"user-service": 10.0, "order-service": 20.0},
            {"order-service": 2.0},
        )
        self.assertIsNone(ratios["user-service"])
        self.assertEqual(ratios["order-service"], 0.1)

    def test_no_traffic_means_unknown_ratio(self):
        ratios = _calculate_error_ratios(
            {"user-service": 0.0},
            {},
        )
        self.assertIsNone(ratios["user-service"])

    def test_errors_above_total_are_rejected(self):
        ratios = _calculate_error_ratios(
            {"user-service": 1.0},
            {"user-service": 2.0},
        )
        self.assertIsNone(ratios["user-service"])

    @patch("ml.prometheus_collector.query_prometheus")
    def test_collect_features_returns_all_services(self, mock_query):
        mock_query.return_value = [sample("user-service", 0.25)]

        result = collect_features()

        self.assertEqual(
            set(result),
            {"user-service", "order-service", "payment-service"},
        )
        self.assertEqual(result["user-service"]["request_rate"], 0.25)
        self.assertIsNone(result["order-service"]["request_rate"])
        self.assertEqual(mock_query.call_count, 3)

    @patch(
        "ml.prometheus_collector.query_prometheus",
        side_effect=PrometheusError("test failure"),
    )
    def test_prometheus_failure_is_reported(self, mock_query):
        with self.assertRaises(PrometheusError):
            collect_features()


if __name__ == "__main__":
    unittest.main()

