"""Tests de la migration 0002 : PumpSchedule, NetMeteringSettlement, CarbonCredit."""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from tunisovereign_core.models import (
    AgentLoopExecution,
    AnomalyAndForecastEvent,
    CarbonCredit,
    CooperativeUnit,
    Feeder,
    NetMeteringSettlement,
    OnChainZKReceipt,
    PumpSchedule,
    ResourceNodePlot,
    StakeholderUser,
)


class Migration0002ModelsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = StakeholderUser.objects.create_user(username="test_owner", password="x")
        cls.feeder = Feeder.objects.create(name="Feeder test", governorate="TOZEUR", capacity_kw=100)
        cls.coop = CooperativeUnit.objects.create(
            name="Coop test", governorate="TOZEUR", daily_quota_limit=500
        )
        cls.node = ResourceNodePlot.objects.create(
            coop=cls.coop, owner=cls.user, feeder=cls.feeder, node_code="TST-001", installed_kwp=10
        )
        cls.t0 = timezone.now().replace(minute=0, second=0, microsecond=0)
        cls.t1 = cls.t0 + timedelta(days=1)

    # --- aides ---
    def _settlement(self, net=3000, start=None, end=None):
        return NetMeteringSettlement.objects.create(
            node=self.node,
            period_start=start or self.t0,
            period_end=end or self.t1,
            imported_kwh=50,
            exported_kwh=20,
            import_cost_millimes=5000,
            export_credit_millimes=2000,
            net_amount_millimes=net,
        )

    def assertRejectedByDatabase(self, func):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                func()

    # --- NetMeteringSettlement ---
    def test_settlement_valid_is_accepted(self):
        settlement = self._settlement(net=3000)
        self.assertEqual(settlement.status, NetMeteringSettlement.Status.PENDING)

    def test_settlement_net_must_equal_import_minus_export(self):
        self.assertRejectedByDatabase(lambda: self._settlement(net=9999))

    def test_settlement_end_must_be_after_start(self):
        self.assertRejectedByDatabase(lambda: self._settlement(start=self.t1, end=self.t0))

    def test_settlement_unique_per_node_and_period(self):
        self._settlement()
        self.assertRejectedByDatabase(lambda: self._settlement())

    def test_settlement_is_protected_from_node_deletion(self):
        self._settlement()
        with self.assertRaises(ProtectedError):
            self.node.delete()

    def test_receipt_defaults_to_unverified_and_links_to_settlement(self):
        run = AgentLoopExecution.objects.create(thread_id="t-chain", trigger_source="test")
        receipt = OnChainZKReceipt.objects.create(
            agent_execution=run,
            zk_commitment_hash="0x" + "a" * 64,
            tx_hash="0x" + "b" * 64,
            block_number=1,
        )
        self.assertFalse(receipt.is_verified_on_chain)
        settlement = self._settlement()
        settlement.zk_receipt = receipt
        settlement.save()
        credit = CarbonCredit.objects.create(
            settlement=settlement, green_kwh=30, co2_avoided_kg=15, emission_factor_kg_per_kwh=0.5
        )
        self.assertEqual(receipt.settlement.carbon_credit, credit)

    # --- CarbonCredit ---
    def test_carbon_credit_valid_is_accepted(self):
        credit = CarbonCredit.objects.create(
            settlement=self._settlement(),
            green_kwh=30,
            co2_avoided_kg=15,
            emission_factor_kg_per_kwh=0.5,
        )
        self.assertEqual(credit.emission_factor_kg_per_kwh, 0.5)

    def test_carbon_credit_factor_must_be_positive(self):
        settlement = self._settlement()
        self.assertRejectedByDatabase(
            lambda: CarbonCredit.objects.create(
                settlement=settlement, green_kwh=30, co2_avoided_kg=0, emission_factor_kg_per_kwh=0
            )
        )

    def test_carbon_credit_only_one_per_settlement(self):
        settlement = self._settlement()
        CarbonCredit.objects.create(
            settlement=settlement, green_kwh=30, co2_avoided_kg=15, emission_factor_kg_per_kwh=0.5
        )
        self.assertRejectedByDatabase(
            lambda: CarbonCredit.objects.create(
                settlement=settlement, green_kwh=10, co2_avoided_kg=5, emission_factor_kg_per_kwh=0.5
            )
        )

    # --- PumpSchedule ---
    def test_pump_schedule_valid_without_agent_run(self):
        schedule = PumpSchedule.objects.create(
            node=self.node, start=self.t0, end=self.t0 + timedelta(hours=2), planned_kw=5
        )
        self.assertEqual(schedule.status, PumpSchedule.Status.PROPOSED)
        self.assertIsNone(schedule.agent_execution)

    def test_pump_schedule_end_must_be_after_start(self):
        self.assertRejectedByDatabase(
            lambda: PumpSchedule.objects.create(
                node=self.node, start=self.t1, end=self.t0, planned_kw=5
            )
        )

    def test_pump_schedule_power_cannot_be_negative(self):
        self.assertRejectedByDatabase(
            lambda: PumpSchedule.objects.create(
                node=self.node, start=self.t0, end=self.t1, planned_kw=-1
            )
        )

    # --- AnomalyAndForecastEvent ---
    def test_feeder_overload_anomaly_has_no_ml_score(self):
        event = AnomalyAndForecastEvent.objects.create(
            feeder=self.feeder, anomaly_type="FEEDER_OVERLOAD", severity="CRITICAL"
        )
        self.assertIsNone(event.isolation_forest_score)