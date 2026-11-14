import os
from datetime import date

from django.core.management.base import BaseCommand

from tunisovereign_core.models import (
    CooperativeUnit,
    Feeder,
    Governorate,
    ResourceNodePlot,
    StakeholderUser,
    Tariff,
)

# Capacités PROVISOIRES (kW) : on les recalibrera avec le simulateur.
FEEDERS = [
    ("Feeder-TOZ-01", Governorate.TOZEUR, 60.0),
    ("Feeder-KEB-01", Governorate.KEBILI, 60.0),
    ("Feeder-TAT-01", Governorate.TATAOUINE, 45.0),
    ("Feeder-SFX-01", Governorate.SFAX, 90.0),
]

# Quotas PROVISOIRES (kWh/jour).
COOPS = [
    ("Coopérative SolarSouk Tozeur", Governorate.TOZEUR, 400.0),
    ("Coopérative SolarSouk Kébili", Governorate.KEBILI, 400.0),
    ("Coopérative SolarSouk Tataouine", Governorate.TATAOUINE, 300.0),
    ("Coopérative SolarSouk Sfax", Governorate.SFAX, 600.0),
]

# Tarifs ILLUSTRATIFS (millimes/kWh), pas des tarifs STEG officiels.
TARIFFS = [
    ("Heures creuses", Tariff.TimeBand.OFFPEAK, 22, 6, 150, 100),
    ("Jour", Tariff.TimeBand.DAY, 6, 18, 200, 130),
    ("Pointe", Tariff.TimeBand.PEAK, 18, 22, 300, 160),
]

# Mot de passe de DÉVELOPPEMENT uniquement (modifiable via SEED_USER_PASSWORD dans .env).
SEED_PASSWORD = os.environ.get("SEED_USER_PASSWORD", "SolarSouk-dev-2026")

# (username, rôle, gouvernorat, accès à l'admin Django)
Role = StakeholderUser.Role
USERS = [
    ("coop_tozeur", Role.COOP_MEMBER, Governorate.TOZEUR, False),
    ("coop_kebili", Role.COOP_MEMBER, Governorate.KEBILI, False),
    ("coop_tataouine", Role.COOP_MEMBER, Governorate.TATAOUINE, False),
    ("coop_sfax", Role.COOP_MEMBER, Governorate.SFAX, False),
    ("auditeur_tozeur", Role.REGIONAL_AUDITOR, Governorate.TOZEUR, False),
    ("admin_national", Role.NATIONAL_ADMIN, Governorate.TOZEUR, True),
    ("agent_service", Role.AGENT_SERVICE, Governorate.TOZEUR, False),
]

# Propriétaire des nœuds de chaque gouvernorat.
OWNERS = {
    Governorate.TOZEUR: "coop_tozeur",
    Governorate.KEBILI: "coop_kebili",
    Governorate.TATAOUINE: "coop_tataouine",
    Governorate.SFAX: "coop_sfax",
}

# (node_code, gouvernorat, type, kWp installés, batterie kWh, puissance pompe kW ; 0 = pas de pompe)
# Valeurs PROVISOIRES, à calibrer avec le simulateur.
NODES = [
    ("TOZ-001", Governorate.TOZEUR, "FARM", 30.0, 40.0, 15.0),
    ("TOZ-002", Governorate.TOZEUR, "FARM", 20.0, 20.0, 11.0),
    ("TOZ-003", Governorate.TOZEUR, "SME", 15.0, 10.0, 0.0),
    ("KEB-001", Governorate.KEBILI, "FARM", 30.0, 40.0, 15.0),
    ("KEB-002", Governorate.KEBILI, "FARM", 25.0, 30.0, 11.0),
    ("KEB-003", Governorate.KEBILI, "SME", 15.0, 10.0, 0.0),
    ("TAT-001", Governorate.TATAOUINE, "FARM", 20.0, 20.0, 11.0),
    ("TAT-002", Governorate.TATAOUINE, "FARM", 15.0, 10.0, 7.5),
    ("SFX-001", Governorate.SFAX, "SME", 40.0, 60.0, 0.0),
    ("SFX-002", Governorate.SFAX, "FARM", 30.0, 40.0, 15.0),
]


class Command(BaseCommand):
    help = "Peuple la base : feeders, coopératives, tarifs, utilisateurs et nœuds (idempotent)."

    def handle(self, *args, **options):
        for name, gov, cap in FEEDERS:
            Feeder.objects.update_or_create(
                name=name, defaults={"governorate": gov, "capacity_kw": cap}
            )

        for name, gov, quota in COOPS:
            CooperativeUnit.objects.update_or_create(
                name=name, defaults={"governorate": gov, "daily_quota_limit": quota}
            )

        for name, band, start, end, buy, sell in TARIFFS:
            Tariff.objects.update_or_create(
                name=name,
                defaults={
                    "time_band": band,
                    "start_hour": start,
                    "end_hour": end,
                    "buy_price_millimes_kwh": buy,
                    "sell_price_millimes_kwh": sell,
                    "valid_from": date(2026, 1, 1),
                },
            )

        for username, role, gov, is_staff in USERS:
            user, created = StakeholderUser.objects.get_or_create(
                username=username,
                defaults={"role": role, "governorate": gov, "is_staff": is_staff},
            )
            if created:
                user.set_password(SEED_PASSWORD)
                user.save()

        for code, gov, site, kwp, batt, pump_kw in NODES:
            ResourceNodePlot.objects.update_or_create(
                node_code=code,
                defaults={
                    "coop": CooperativeUnit.objects.get(governorate=gov),
                    "owner": StakeholderUser.objects.get(username=OWNERS[gov]),
                    "feeder": Feeder.objects.get(governorate=gov),
                    "site_type": site,
                    "installed_kwp": kwp,
                    "battery_capacity_kwh": batt,
                    "has_pump": pump_kw > 0,
                    "pump_rated_kw": pump_kw,
                },
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seed OK : {Feeder.objects.count()} feeders, "
            f"{CooperativeUnit.objects.count()} coopératives, {Tariff.objects.count()} tarifs, "
            f"{StakeholderUser.objects.count()} utilisateurs, {ResourceNodePlot.objects.count()} nœuds."
        ))