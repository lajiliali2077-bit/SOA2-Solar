"""
Tests de la vraie forecast_peak_load, SANS base de données : on teste le calcul pur
(_forecast_from_history) avec des historiques synthétiques dont le résultat est connu d'avance.

Lancement depuis la racine du dépôt :
    python -m unittest agent.skills.test_irradiance_forecaster -v
"""
import unittest
from datetime import datetime, timedelta, timezone

from agent.skills import irradiance_forecaster as fc

UTC = timezone.utc
START = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)
CONTRACT_KEYS = {
    "feeder_id", "horizon_hours", "hourly", "peak_kw", "peak_pct", "forecasted_deficit_24h_kwh",
}


def make_series(days, value_of):
    """Série {horodatage UTC: valeur} sur `days` jours, 96 créneaux de 15 min par jour."""
    base = datetime(2026, 11, 1, tzinfo=UTC)
    return {
        base + timedelta(days=d, minutes=15 * slot): value_of(slot, d)
        for d in range(days)
        for slot in range(fc.SLOTS_PER_DAY)
    }


def forecast(net, gen=None, capacity=50.0, horizon=24):
    gen = gen if gen is not None else make_series(5, lambda slot, day: 0.0)
    return fc._forecast_from_history(1, capacity, horizon, START, net, gen)


class ForecastContractTests(unittest.TestCase):
    def test_result_has_exactly_the_contract_keys(self):
        result = forecast(make_series(5, lambda s, d: 20.0))
        self.assertEqual(set(result), CONTRACT_KEYS)
        self.assertEqual(result["feeder_id"], 1)
        self.assertEqual(result["horizon_hours"], 24)

    def test_hourly_points_have_one_entry_per_hour_in_utc(self):
        result = forecast(make_series(5, lambda s, d: 20.0), horizon=30)
        hours = [datetime.fromisoformat(p["hour"]) for p in result["hourly"]]
        self.assertEqual(len(hours), 30)
        self.assertTrue(all(h.utcoffset() == timedelta(0) for h in hours))
        self.assertTrue(all(b - a == timedelta(hours=1) for a, b in zip(hours, hours[1:])))
        self.assertEqual(set(result["hourly"][0]), {"hour", "load_kw", "generation_kw"})

    def test_horizon_is_validated_before_touching_the_database(self):
        for bad in (0, 169, -1):
            with self.assertRaises(ValueError):
                fc.forecast_peak_load(1, horizon_hours=bad)


class OverloadTests(unittest.TestCase):
    def test_evening_overload_is_predicted(self):
        # Capacité 50 kW, limite 46 kW. De 18h00 à 18h45 UTC (créneaux 72 à 75) : 49 kW, sinon 10 kW.
        net = make_series(5, lambda s, d: 49.0 if 72 <= s <= 75 else 10.0)
        result = forecast(net)
        self.assertEqual(result["peak_kw"], 49.0)
        self.assertEqual(result["peak_pct"], 98.0)
        # 4 pas x (49 - 46) kW x 0,25 h = 3,0 kWh
        self.assertEqual(result["forecasted_deficit_24h_kwh"], 3.0)

    def test_no_overload_means_zero_deficit(self):
        result = forecast(make_series(5, lambda s, d: 20.0))
        self.assertEqual(result["peak_pct"], 40.0)
        self.assertEqual(result["forecasted_deficit_24h_kwh"], 0.0)

    def test_load_exactly_at_the_threshold_is_not_a_deficit(self):
        result = forecast(make_series(5, lambda s, d: 46.0))  # 92 % de 50 kW
        self.assertEqual(result["forecasted_deficit_24h_kwh"], 0.0)


class ProfileTests(unittest.TestCase):
    def test_median_ignores_a_single_outlier_day(self):
        # Le jour 0 a une valeur aberrante de 90 kW au créneau 40 ; les 4 autres jours : 20 kW.
        net = make_series(5, lambda s, d: 90.0 if (d == 0 and s == 40) else 20.0)
        self.assertEqual(forecast(net)["peak_kw"], 20.0)

    def test_hourly_load_is_the_peak_of_its_four_slots(self):
        # Un seul créneau à 40 kW (10h30 UTC) : la charge de l'heure 10 doit être 40, pas la moyenne.
        net = make_series(5, lambda s, d: 40.0 if s == 42 else 10.0)
        hourly = forecast(net)["hourly"]
        self.assertEqual(hourly[10]["load_kw"], 40.0)
        self.assertEqual(hourly[9]["load_kw"], 10.0)

    def test_generation_is_the_mean_of_the_hour(self):
        gen = make_series(5, lambda s, d: {0: 0.0, 1: 4.0, 2: 8.0, 3: 12.0}.get(s, 0.0))
        net = make_series(5, lambda s, d: 10.0)
        self.assertEqual(forecast(net, gen)["hourly"][0]["generation_kw"], 6.0)

    def test_profile_repeats_after_24_hours(self):
        net = make_series(5, lambda s, d: float(s))  # charge différente à chaque créneau
        hourly = forecast(net, horizon=48)["hourly"]
        for i in range(24):
            self.assertEqual(hourly[i]["load_kw"], hourly[i + 24]["load_kw"])

    def test_slots_are_computed_in_utc(self):
        # 01h00 à UTC+1 = 00h00 UTC = créneau 0
        local = datetime(2026, 11, 10, 1, 0, tzinfo=timezone(timedelta(hours=1)))
        self.assertEqual(fc._median_profile({local: 7.0}), {0: 7.0})

    def test_incomplete_history_raises_instead_of_inventing_data(self):
        partial = {
            datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=15 * s): 20.0 for s in range(10)
        }
        with self.assertRaises(ValueError):
            forecast(partial)


if __name__ == "__main__":
    unittest.main()