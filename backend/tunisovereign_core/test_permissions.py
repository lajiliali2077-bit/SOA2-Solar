"""
Tests automatiques des permissions par rôle (Rôle 2, incrément 1).

Lancer depuis le dossier backend :
    python manage.py test tunisovereign_core.test_permissions -v 2

Codes à connaître :  200 = autorisé | 201 = créé | 400 = demande invalide
                     401 = pas connecté | 403 = connecté mais interdit
"""
from django.test import TestCase
from rest_framework.test import APIClient

from .models import (
    AnomalyAndForecastEvent,
    CooperativeUnit,
    Feeder,
    ResourceNodePlot,
    StakeholderUser,
)
from .permissions import (
    anomalies_visible_to,
    cooperatives_visible_to,
    feeders_visible_to,
    nodes_visible_to,
    readings_visible_to,
)

MOT_DE_PASSE = "Dev-Pass-12345!"


class BaseCase(TestCase):
    """Petit réseau de test : 2 gouvernorats, 3 nœuds, un utilisateur par rôle."""

    @classmethod
    def setUpTestData(cls):
        User = StakeholderUser
        cls.coop_toz = User.objects.create_user("coop_toz", password=MOT_DE_PASSE, role="COOP_MEMBER", governorate="TOZEUR")
        cls.coop_toz2 = User.objects.create_user("coop_toz2", password=MOT_DE_PASSE, role="COOP_MEMBER", governorate="TOZEUR")
        cls.coop_sfx = User.objects.create_user("coop_sfx", password=MOT_DE_PASSE, role="COOP_MEMBER", governorate="SFAX")
        cls.auditeur = User.objects.create_user("auditeur_toz", password=MOT_DE_PASSE, role="REGIONAL_AUDITOR", governorate="TOZEUR")
        cls.admin = User.objects.create_user("admin_nat", password=MOT_DE_PASSE, role="NATIONAL_ADMIN", governorate="TOZEUR")
        cls.agent = User.objects.create_user("agent_svc", password=MOT_DE_PASSE, role="AGENT_SERVICE", governorate="TOZEUR")

        cls.feeder_toz = Feeder.objects.create(name="F-TOZ", governorate="TOZEUR", capacity_kw=100)
        cls.feeder_sfx = Feeder.objects.create(name="F-SFX", governorate="SFAX", capacity_kw=100)
        cls.cooperative_toz = CooperativeUnit.objects.create(name="Coop Tozeur", governorate="TOZEUR", daily_quota_limit=500)
        cls.cooperative_sfx = CooperativeUnit.objects.create(name="Coop Sfax", governorate="SFAX", daily_quota_limit=500)

        def noeud(code, owner, coop, feeder):
            return ResourceNodePlot.objects.create(
                node_code=code, owner=owner, coop=coop, feeder=feeder, installed_kwp=10
            )

        cls.n1 = noeud("TOZ-001", cls.coop_toz, cls.cooperative_toz, cls.feeder_toz)
        cls.n2 = noeud("TOZ-002", cls.coop_toz2, cls.cooperative_toz, cls.feeder_toz)
        cls.n3 = noeud("SFX-001", cls.coop_sfx, cls.cooperative_sfx, cls.feeder_sfx)

        cls.anomalie_toz = AnomalyAndForecastEvent.objects.create(
            feeder=cls.feeder_toz, anomaly_type="FEEDER_OVERLOAD", severity="CRITICAL", isolation_forest_score=-0.5
        )
        cls.anomalie_sfx = AnomalyAndForecastEvent.objects.create(
            node=cls.n3, anomaly_type="INVERTER_FAILURE", severity="MEDIUM", isolation_forest_score=-0.2
        )

    def client_de(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def codes_nodes(self, user):
        reponse = self.client_de(user).get("/api/v1/nodes/")
        self.assertEqual(reponse.status_code, 200)
        return sorted(n["node_code"] for n in reponse.data["results"])


class NodesTests(BaseCase):
    def test_anonyme_refuse(self):
        self.assertEqual(self.client_de(None).get("/api/v1/nodes/").status_code, 401)

    def test_membre_ne_voit_que_ses_noeuds(self):
        self.assertEqual(self.codes_nodes(self.coop_toz), ["TOZ-001"])
        self.assertEqual(self.codes_nodes(self.coop_toz2), ["TOZ-002"])
        self.assertEqual(self.codes_nodes(self.coop_sfx), ["SFX-001"])

    def test_auditeur_voit_son_gouvernorat(self):
        self.assertEqual(self.codes_nodes(self.auditeur), ["TOZ-001", "TOZ-002"])

    def test_admin_et_agent_voient_tout(self):
        tout = ["SFX-001", "TOZ-001", "TOZ-002"]
        self.assertEqual(self.codes_nodes(self.admin), tout)
        self.assertEqual(self.codes_nodes(self.agent), tout)

    def test_detail_d_un_noeud(self):
        c = self.client_de(self.coop_toz)
        self.assertEqual(c.get(f"/api/v1/nodes/{self.n1.id}/").status_code, 200)  # le sien
        self.assertEqual(c.get(f"/api/v1/nodes/{self.n2.id}/").status_code, 403)  # celui d'un collègue
        self.assertEqual(c.get(f"/api/v1/nodes/{self.n3.id}/").status_code, 403)  # un autre gouvernorat

        a = self.client_de(self.auditeur)
        self.assertEqual(a.get(f"/api/v1/nodes/{self.n2.id}/").status_code, 200)
        self.assertEqual(a.get(f"/api/v1/nodes/{self.n3.id}/").status_code, 403)

        self.assertEqual(self.client_de(self.admin).get(f"/api/v1/nodes/{self.n3.id}/").status_code, 200)

    def test_personne_n_ecrit_sur_les_noeuds(self):
        for user in (self.coop_toz, self.auditeur, self.admin, self.agent):
            reponse = self.client_de(user).post("/api/v1/nodes/", {}, format="json")
            self.assertEqual(reponse.status_code, 403, user.username)


class CooperativesTests(BaseCase):
    def noms(self, user):
        reponse = self.client_de(user).get("/api/v1/cooperatives/")
        self.assertEqual(reponse.status_code, 200)
        return sorted(c["name"] for c in reponse.data["results"])

    def test_liste_selon_le_role(self):
        self.assertEqual(self.noms(self.coop_toz), ["Coop Tozeur"])
        self.assertEqual(self.noms(self.coop_sfx), ["Coop Sfax"])
        self.assertEqual(self.noms(self.auditeur), ["Coop Tozeur"])
        self.assertEqual(self.noms(self.admin), ["Coop Sfax", "Coop Tozeur"])
        self.assertEqual(self.noms(self.agent), ["Coop Sfax", "Coop Tozeur"])

    def test_detail(self):
        c = self.client_de(self.coop_toz)
        self.assertEqual(c.get(f"/api/v1/cooperatives/{self.cooperative_toz.id}/").status_code, 200)
        self.assertEqual(c.get(f"/api/v1/cooperatives/{self.cooperative_sfx.id}/").status_code, 403)

    def test_anonyme_refuse(self):
        self.assertEqual(self.client_de(None).get("/api/v1/cooperatives/").status_code, 401)


class AnomaliesTests(BaseCase):
    def test_lecture_selon_le_role(self):
        self.assertEqual(self.client_de(None).get("/api/v1/anomalies/").status_code, 401)
        self.assertEqual(self.client_de(self.coop_toz).get("/api/v1/anomalies/").status_code, 403)

        reponse = self.client_de(self.auditeur).get("/api/v1/anomalies/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([a["id"] for a in reponse.data["results"]], [self.anomalie_toz.id])

        for user in (self.admin, self.agent):
            reponse = self.client_de(user).get("/api/v1/anomalies/")
            self.assertEqual(reponse.status_code, 200)
            self.assertEqual(reponse.data["count"], 2)

    def test_detail_hors_gouvernorat_interdit_a_l_auditeur(self):
        a = self.client_de(self.auditeur)
        self.assertEqual(a.get(f"/api/v1/anomalies/{self.anomalie_toz.id}/").status_code, 200)
        self.assertEqual(a.get(f"/api/v1/anomalies/{self.anomalie_sfx.id}/").status_code, 403)

    def donnees(self):
        return {
            "feeder": self.feeder_toz.id,
            "anomaly_type": "FEEDER_OVERLOAD",
            "severity": "CRITICAL",
            "isolation_forest_score": -0.7,
        }

    def test_ecriture_selon_le_role(self):
        self.assertEqual(self.client_de(None).post("/api/v1/anomalies/", self.donnees(), format="json").status_code, 401)
        self.assertEqual(self.client_de(self.coop_toz).post("/api/v1/anomalies/", self.donnees(), format="json").status_code, 403)
        self.assertEqual(self.client_de(self.auditeur).post("/api/v1/anomalies/", self.donnees(), format="json").status_code, 403)
        self.assertEqual(self.client_de(self.agent).post("/api/v1/anomalies/", self.donnees(), format="json").status_code, 201)
        self.assertEqual(self.client_de(self.admin).post("/api/v1/anomalies/", self.donnees(), format="json").status_code, 201)

    def test_ecriture_sans_noeud_ni_feeder_refusee(self):
        donnees = self.donnees()
        del donnees["feeder"]
        reponse = self.client_de(self.agent).post("/api/v1/anomalies/", donnees, format="json")
        self.assertEqual(reponse.status_code, 400)


class DeBoutEnBout(BaseCase):
    def test_jeton_reel_obtenu_par_login(self):
        """On se connecte pour de vrai, puis on utilise le jeton reçu."""
        client = APIClient()
        r = client.post("/api/auth/login/", {"username": "coop_toz", "password": MOT_DE_PASSE}, format="json")
        self.assertEqual(r.status_code, 200)
        client.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
        reponse = client.get("/api/v1/nodes/")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([n["node_code"] for n in reponse.data["results"]], ["TOZ-001"])


class FonctionsPourGraphQL(BaseCase):
    """Les fonctions xxx_visible_to que le Rôle 3 pourra réutiliser."""

    def test_feeders_et_cooperatives(self):
        self.assertEqual(list(feeders_visible_to(self.coop_toz)), [self.feeder_toz])
        self.assertEqual(list(feeders_visible_to(self.auditeur)), [self.feeder_toz])
        self.assertEqual(feeders_visible_to(self.admin).count(), 2)
        self.assertEqual(list(cooperatives_visible_to(self.coop_sfx)), [self.cooperative_sfx])

    def test_noeuds_et_anomalies(self):
        self.assertEqual(list(nodes_visible_to(self.coop_toz)), [self.n1])
        self.assertEqual(list(anomalies_visible_to(self.auditeur)), [self.anomalie_toz])
        self.assertEqual(anomalies_visible_to(self.coop_toz).count(), 0)
        self.assertEqual(readings_visible_to(self.coop_toz).count(), 0)  # aucune mesure dans ce jeu de test

    def test_inconnu_ne_voit_rien(self):
        from django.contrib.auth.models import AnonymousUser

        anonyme = AnonymousUser()
        self.assertEqual(nodes_visible_to(anonyme).count(), 0)
        self.assertEqual(feeders_visible_to(anonyme).count(), 0)
        self.assertEqual(anomalies_visible_to(anonyme).count(), 0)