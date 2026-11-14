"""Tests du stub forecast_peak_load : le contrat d'interface doit être respecté."""
import unittest
from datetime import datetime, timedelta

from agent.skills.irradiance_forecaster import (
    OVERLOAD_THRESHOLD_PCT,
    STUB_CAPACITY_KW,
    forecast_peak_load,
)

EXPECTED_KEYS = {
    "feeder_id",
    "horizon_hours",
    "hourly",
    "peak_kw",
    "peak_pct",
    "forecasted_deficit_24h_kwh",
}


class ForecastPeakLoadStubTests(unittest.TestCase):
    def test_result_has_exactly_the_contract_keys(self):
        result = forecast_peak_load(1)
        self.assertEqual(set(result.keys()), EXPECTED_KEYS)
        self.assertEqual(result["feeder_id"], 1)
        self.assertEqual(result["horizon_hours"], 24)

    def test_default_horizon_gives_24_hourly_points(self):
        self.assertEqual(len(forecast_peak_load(1)["hourly"]), 24)

    def test_other_horizon_is_respected(self):
        result = forecast_peak_load(2, horizon_hours=48)
        self.assertEqual(len(result["hourly"]), 48)
        self.assertEqual(result["horizon_hours"], 48)

    def test_hourly_points_are_utc_and_one_hour_apart(self):
        hourly = forecast_peak_load(1)["hourly"]
        times = [datetime.fromisoformat(point["hour"]) for point in hourly]
        for moment in times:
            self.assertEqual(moment.utcoffset(), timedelta(0))
        for before, after in zip(times, times[1:]):
            self.assertEqual(after - before, timedelta(hours=1))
        for point in hourly:
            self.assertEqual(set(point.keys()), {"hour", "load_kw", "generation_kw"})

    def test_peak_matches_the_hourly_maximum(self):
        result = forecast_peak_load(1)
        self.assertEqual(result["peak_kw"], max(p["load_kw"] for p in result["hourly"]))
        self.assertAlmostEqual(
            result["peak_pct"], result["peak_kw"] / STUB_CAPACITY_KW * 100.0, places=1
        )

    def test_deficit_is_energy_above_the_threshold(self):
        result = forecast_peak_load(1)
        limit_kw = STUB_CAPACITY_KW * OVERLOAD_THRESHOLD_PCT / 100.0
        expected = sum(max(0.0, p["load_kw"] - limit_kw) for p in result["hourly"])
        self.assertGreaterEqual(result["forecasted_deficit_24h_kwh"], 0.0)
        self.assertAlmostEqual(result["forecasted_deficit_24h_kwh"], expected, places=2)

    def test_stub_exposes_an_overload_for_the_agent_to_fix(self):
        self.assertGreater(forecast_peak_load(1)["peak_pct"], OVERLOAD_THRESHOLD_PCT)

    def test_invalid_horizon_is_rejected(self):
        with self.assertRaises(ValueError):
            forecast_peak_load(1, horizon_hours=0)
        with self.assertRaises(ValueError):
            forecast_peak_load(1, horizon_hours=500)


if __name__ == "__main__":
    unittest.main()