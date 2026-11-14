"""
Tests automatiques de l'authentification (Rôle 2, incrément 1).

Lancer depuis le dossier backend :
    python manage.py test tunisovereign_core.test_auth -v 2

Django crée une base de test temporaire et vide, puis la supprime :
ta base de développement n'est jamais touchée.
"""
import base64
import json

from django.test import TestCase
from rest_framework.test import APIClient

from .models import StakeholderUser

MOT_DE_PASSE = "Dev-Pass-12345!"
MOT_DE_PASSE_SOLIDE = "Tr3s-Solide-98!"


def lire_jeton(jeton):
    """Ouvre un jeton JWT et renvoie les informations qu'il contient."""
    partie = jeton.split(".")[1]
    partie += "=" * (-len(partie) % 4)
    return json.loads(base64.urlsafe_b64decode(partie))


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        StakeholderUser.objects.create_user(
            username="coop_tozeur",
            password=MOT_DE_PASSE,
            role=StakeholderUser.Role.COOP_MEMBER,
            governorate="TOZEUR",
        )

    def se_connecter(self, username="coop_tozeur", password=MOT_DE_PASSE):
        return self.client.post(
            "/api/auth/login/", {"username": username, "password": password}, format="json"
        )

    # --- Connexion -------------------------------------------------------
    def test_connexion_ok_et_contenu_du_jeton(self):
        r = self.se_connecter()
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        contenu = lire_jeton(r.data["access"])
        self.assertEqual(contenu["role"], "COOP_MEMBER")
        self.assertEqual(contenu["governorate"], "TOZEUR")

    def test_connexion_mauvais_mot_de_passe(self):
        self.assertEqual(self.se_connecter(password="faux").status_code, 401)

    def test_connexion_utilisateur_inconnu(self):
        self.assertEqual(self.se_connecter(username="fantome").status_code, 401)

    # --- Rafraîchissement ------------------------------------------------
    def test_refresh_donne_un_nouveau_jeton(self):
        r = self.se_connecter()
        r2 = self.client.post("/api/auth/refresh/", {"refresh": r.data["refresh"]}, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("access", r2.data)

    # --- Inscription -----------------------------------------------------
    def test_inscription_ok(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "nouveau", "password": MOT_DE_PASSE_SOLIDE, "governorate": "SFAX"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("password", r.data)  # le mot de passe n'est jamais renvoyé
        u = StakeholderUser.objects.get(username="nouveau")
        self.assertEqual(u.role, "COOP_MEMBER")
        self.assertEqual(u.governorate, "SFAX")
        self.assertNotEqual(u.password, MOT_DE_PASSE_SOLIDE)  # stocké chiffré
        self.assertEqual(self.se_connecter("nouveau", MOT_DE_PASSE_SOLIDE).status_code, 200)

    def test_inscription_impossible_de_choisir_son_role(self):
        r = self.client.post(
            "/api/auth/register/",
            {
                "username": "pirate",
                "password": MOT_DE_PASSE_SOLIDE,
                "role": "NATIONAL_ADMIN",
                "is_staff": True,
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        u = StakeholderUser.objects.get(username="pirate")
        self.assertEqual(u.role, "COOP_MEMBER")
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)

    def test_inscription_mot_de_passe_trop_faible(self):
        r = self.client.post("/api/auth/register/", {"username": "faible", "password": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_inscription_nom_deja_pris(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "coop_tozeur", "password": MOT_DE_PASSE_SOLIDE},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_inscription_gouvernorat_invalide(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "x1", "password": MOT_DE_PASSE_SOLIDE, "governorate": "PARIS"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_inscription_ignore_un_jeton_perime(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer nimportequoi")
        r = self.client.post(
            "/api/auth/register/",
            {"username": "z9", "password": MOT_DE_PASSE_SOLIDE},
            format="json",
        )
        self.assertEqual(r.status_code, 201)