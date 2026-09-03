"""Données pilotes ISMI via le début du workflow officiel d'admission."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from admissions.forms import CandidatureForm
from admissions.models import Candidature
from branches.models import Branch
from core.services.business_data_reset import assert_safe_local_development_database
from formations.models import Programme
from inscriptions.models import Inscription
from inscriptions.services import create_inscription_from_candidature
from payments.models import FinancialLog, Payment, PaymentAgent
from payments.services.cash import validate_cash_code, verify_agent_and_create_session
from students.services.create_student import create_student_after_first_payment
from students.models import Student


PILOT_ACADEMIC_YEAR = "2099-2100"
PILOT_BRANCH_CODE = "MBG"
PILOT_PROGRAMME_SLUG = "infirmiere-sante-maternelle-infantile"
PILOT_CLASS_NAME = "PILOTE ISMI - L1"
PILOT_PAYMENT_AGENT_USERNAME = "mariamcisse"

# 130 000 FCFA d'inscription puis 8 tranches de 35 000 FCFA : 410 000 FCFA.
# Chaque dossier est soldé ou partiellement réglé, sans jamais dépasser ce total.
PAYMENT_SCENARIOS = {
    1: (410_000,), 2: (130_000, 280_000), 3: (200_000, 210_000),
    4: (410_000,), 5: (155_000, 255_000), 6: (130_000, 70_000, 210_000),
    7: (305_000,), 8: (130_000, 175_000), 9: (200_000, 105_000),
    10: (305_000,), 11: (150_000, 155_000), 12: (200_000,),
    13: (130_000, 70_000), 14: (200_000,), 15: (50_000, 150_000),
    16: (130_000,), 17: (130_000,), 18: (130_000,),
    19: (165_000,), 20: (130_000,),
}
PILOT_COMMENT = "DONNÉES PILOTES / NON DESTINÉES À LA PRODUCTION - ISMI L1"

PILOT_STUDENTS = (
    ("Moussa", "Dembélé", "male", "2004-03-14", "Bamako", "Kalaban Coura, Bamako", "moussa.dembele01@example.com"),
    ("Fatoumata", "Traoré", "female", "2003-07-22", "Sikasso", "Magnambougou, Bamako", "fatoumata.traore02@example.com"),
    ("Aminata", "Coulibaly", "female", "2004-11-09", "Ségou", "Banankabougou, Bamako", "aminata.coulibaly03@example.com"),
    ("Ibrahim", "Diarra", "male", "2003-01-18", "Kayes", "Moribabougou", "ibrahim.diarra04@example.com"),
    ("Mariam", "Konaté", "female", "2004-05-27", "Koulikoro", "Moribabougou", "mariam.konate05@example.com"),
    ("Oumar", "Keïta", "male", "2002-09-03", "Bamako", "Djélibougou, Bamako", "oumar.keita06@example.com"),
    ("Aïssata", "Diallo", "female", "2003-12-16", "Mopti", "Sangarébougou", "aissata.diallo07@example.com"),
    ("Mamadou", "Sangaré", "male", "2004-04-11", "Koutiala", "Titibougou, Bamako", "mamadou.sangare08@example.com"),
    ("Kadidia", "Sidibé", "female", "2003-08-30", "Bamako", "Niamana, Bamako", "kadidia.sidibe09@example.com"),
    ("Adama", "Camara", "male", "2004-02-07", "Kita", "Moribabougou", "adama.camara10@example.com"),
    ("Fanta", "Maïga", "female", "2003-06-19", "Gao", "Boulkassoumbougou, Bamako", "fanta.maiga11@example.com"),
    ("Boubacar", "Touré", "male", "2002-10-25", "Ségou", "Faladié, Bamako", "boubacar.toure12@example.com"),
    ("Hawa", "Cissé", "female", "2004-01-12", "Bamako", "Sotuba, Bamako", "hawa.cisse13@example.com"),
    ("Abdoulaye", "Coulibaly", "male", "2003-08-08", "Bougouni", "Moribabougou", "abdoulaye.coulibaly14@example.com"),
    ("Rokia", "Diabaté", "female", "2004-04-21", "Sikasso", "Yirimadio, Bamako", "rokia.diabate15@example.com"),
    ("Modibo", "Doumbia", "male", "2003-12-05", "Koulikoro", "Moribabougou", "modibo.doumbia16@example.com"),
    ("Kadiatou", "Samaké", "female", "2004-03-17", "Bamako", "Missabougou, Bamako", "kadiatou.samake17@example.com"),
    ("Souleymane", "Koné", "male", "2002-09-29", "San", "Moribabougou", "souleymane.kone18@example.com"),
    ("Fatimata", "Bagayoko", "female", "2004-06-06", "Kita", "Sébénikoro, Bamako", "fatimata.bagayoko19@example.com"),
    ("Yacouba", "Sissoko", "male", "2003-11-13", "Kayes", "Moribabougou", "yacouba.sissoko20@example.com"),
)


class Command(BaseCommand):
    help = "Crée les candidatures pilotes ISMI via le workflow d'admission, sans paiement fictif."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("DONNÉES PILOTES / NON DESTINÉES À LA PRODUCTION"))
        assert_safe_local_development_database()

        branch = Branch.objects.filter(code=PILOT_BRANCH_CODE, is_active=True).first()
        programme = Programme.objects.filter(slug=PILOT_PROGRAMME_SLUG, is_active=True).first()
        academic_class = AcademicClass.objects.filter(
            branch=branch,
            programme=programme,
            academic_year__name=PILOT_ACADEMIC_YEAR,
            name=PILOT_CLASS_NAME,
            level="L1",
            is_active=True,
        ).first()
        if branch is None or programme is None or academic_class is None:
            raise CommandError("Contexte pilote ISMI Moribabougou incomplet.")
        if programme.required_documents.exists():
            raise CommandError(
                "Documents requis configurés pour ISMI : le seed refuse de créer de faux documents officiels."
            )

        payment_agent = PaymentAgent.objects.filter(
            user__username=PILOT_PAYMENT_AGENT_USERNAME,
            branch=branch,
            is_active=True,
        ).select_related("user").first()
        if payment_agent is None:
            raise CommandError("Agente de paiement Mariam Cisse active absente a Moribabougou.")

        created = 0
        reused = 0
        inscriptions_created = 0
        inscriptions_reused = 0
        payments_created = 0
        payments_reused = 0
        cash_codes_used = 0
        with transaction.atomic():
            for index, student_data in enumerate(PILOT_STUDENTS, start=1):
                candidature, was_created = self._upsert_admission(
                    branch=branch,
                    programme=programme,
                    index=index,
                    student_data=student_data,
                )
                created += int(was_created)
                reused += int(not was_created)
                self._accept_candidature(candidature)
                inscription, inscription_was_created = self._ensure_inscription(
                    candidature=candidature,
                    academic_class=academic_class,
                    amount_due=programme.get_inscription_amount_for_year(1),
                )
                inscriptions_created += int(inscription_was_created)
                inscriptions_reused += int(not inscription_was_created)
                created_count, reused_count, used_codes = self._ensure_payments(
                    inscription=inscription,
                    amounts=PAYMENT_SCENARIOS[index],
                    agent=payment_agent,
                    branch=branch,
                )
                payments_created += created_count
                payments_reused += reused_count
                cash_codes_used += used_codes
                self._ensure_student_and_enrollment(inscription)

        fee_amount = programme.get_inscription_amount_for_year(1)
        if fee_amount != 410_000:
            raise CommandError(f"Tarification ISMI L1 incoherente : {fee_amount} FCFA.")
        self._verify_database(
            branch=branch,
            programme=programme,
            academic_class=academic_class,
            expected_payments=sum(len(amounts) for amounts in PAYMENT_SCENARIOS.values()),
            payment_agent=payment_agent,
        )
        self.stdout.write(f"Candidatures : {created} creees, {reused} reutilisees.")
        self.stdout.write(f"Inscriptions : {inscriptions_created} creees, {inscriptions_reused} reutilisees.")
        self.stdout.write(f"Paiements valides : {payments_created} crees, {payments_reused} reutilises.")
        self.stdout.write(f"Codes especes generes et consommes : {cash_codes_used}.")
        return
        self.stdout.write(f"Candidatures : {created} créées, {reused} réutilisées.")
        if not fee_amount:
            self.stdout.write(self.style.WARNING(
                "TARIFICATION MANQUANTE — impossible de créer des paiements fiables."
            ))
            self.stdout.write(
                "Arrêt au dernier état légitime : candidatures acceptées, sans inscription ni paiement."
            )
            return

        raise CommandError(
            "Une tarification est désormais configurée. Cette commande doit être étendue "
            "avec les scénarios de paiement officiels avant toute écriture financière."
        )

    def _upsert_admission(self, *, branch, programme, index, student_data):
        first_name, last_name, gender, birth_date, birth_place, address, email = student_data
        existing = Candidature.objects.filter(
            email=email,
            programme=programme,
            academic_year=PILOT_ACADEMIC_YEAR,
        ).first()
        if existing:
            return existing, False

        form = CandidatureForm(
            data={
                "branch": branch.pk,
                "first_name": first_name,
                "last_name": last_name,
                "gender": gender,
                "birth_date": birth_date,
                "birth_place": birth_place,
                "phone": f"TEST-ISMI-{index:02d}",
                "email": email,
                "address": address,
                "city": "Bamako",
                "country": "Mali",
            }
        )
        if not form.is_valid():
            raise CommandError(f"Candidature pilote invalide pour {email} : {form.errors.as_text()}")

        candidature = form.save(commit=False)
        candidature.programme = programme
        candidature.academic_year = PILOT_ACADEMIC_YEAR
        candidature.entry_year = 1
        candidature.admin_comment = PILOT_COMMENT
        candidature.save()
        return candidature, True

    def _accept_candidature(self, candidature):
        if candidature.status == "accepted":
            return
        if candidature.status not in {"submitted", "under_review"}:
            raise CommandError(
                f"Candidature pilote {candidature.email} dans un état non rejouable : {candidature.status}."
            )
        if candidature.status == "submitted":
            candidature.status = "under_review"
            candidature.save(update_fields=["status", "updated_at"])
        candidature.status = "accepted"
        candidature.reviewed_at = timezone.now()
        candidature.admin_comment = PILOT_COMMENT
        candidature.save(update_fields=["status", "reviewed_at", "admin_comment", "updated_at"])

    def _ensure_inscription(self, *, candidature, academic_class, amount_due):
        if amount_due != 410_000:
            raise CommandError(f"Tarification ISMI L1 incoherente : {amount_due} FCFA.")

        existing = Inscription.objects.filter(candidature=candidature).first()
        if existing:
            if existing.academic_class_id != academic_class.id or existing.amount_due != amount_due:
                raise CommandError(
                    f"Inscription existante incoherente pour {candidature.email}; aucune correction automatique."
                )
            return existing, False

        try:
            inscription = create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due,
                academic_class=academic_class,
                status=Inscription.STATUS_AWAITING_PAYMENT,
            )
        except ValidationError as exc:
            raise CommandError(f"Inscription impossible pour {candidature.email} : {exc}") from exc
        return inscription, True

    def _ensure_payments(self, *, inscription, amounts, agent, branch):
        existing = list(
            inscription.payments.filter(status=Payment.STATUS_VALIDATED).order_by("created_at", "id")
        )
        existing_amounts = tuple(payment.amount for payment in existing)
        if existing_amounts and existing_amounts != tuple(amounts[:len(existing_amounts)]):
            raise CommandError(
                f"Paiements existants incoherents pour l'inscription {inscription.pk}; aucune duplication."
            )
        if len(existing_amounts) > len(amounts):
            raise CommandError(f"Trop de paiements existants pour l'inscription {inscription.pk}.")

        created = 0
        agent_name = agent.user.get_full_name()
        for amount in amounts[len(existing_amounts):]:
            if amount > inscription.balance:
                raise CommandError(f"Paiement de {amount} FCFA superieur au solde restant.")
            resolved_agent, error = verify_agent_and_create_session(inscription, agent_name)
            if error or resolved_agent != agent:
                raise CommandError(error or "Agente de paiement ISMI incoherente.")
            session = inscription.cash_sessions.filter(
                agent=agent,
                is_used=False,
            ).order_by("-created_at").first()
            if session is None:
                raise CommandError("Session especes ISMI introuvable apres generation du code.")
            session, error = validate_cash_code(inscription, agent, session.verification_code)
            if error:
                raise CommandError(error)
            payment = Payment.objects.create(
                inscription=inscription,
                amount=amount,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
                paid_at=timezone.now(),
                agent=agent,
                cash_session=session,
            )
            FinancialLog.objects.create(
                branch=branch,
                payment=payment,
                action=FinancialLog.ACTION_PAYMENT_CREATED,
                new_amount=payment.amount,
                reason="Paiement ISMI pilote cree et valide par le workflow caisse.",
                actor=agent.user,
                metadata={"payment_reference": payment.reference, "inscription_id": inscription.id},
            )
            created += 1
            inscription.refresh_from_db()
        return created, len(existing_amounts), created

    def _verify_database(self, *, branch, programme, academic_class, expected_payments, payment_agent):
        candidatures = Candidature.objects.filter(
            branch=branch,
            programme=programme,
            academic_year=PILOT_ACADEMIC_YEAR,
        )
        inscriptions = Inscription.objects.filter(
            candidature__in=candidatures,
            academic_class=academic_class,
            amount_due=410_000,
        )
        payments = Payment.objects.filter(inscription__in=inscriptions, status=Payment.STATUS_VALIDATED)
        enrollments = AcademicEnrollment.objects.filter(inscription__in=inscriptions, academic_class=academic_class)
        students = Student.objects.filter(inscription__in=inscriptions)
        if candidatures.count() != 20 or candidatures.exclude(status="accepted").exists():
            raise CommandError("Les 20 candidatures ISMI ne sont pas toutes acceptees.")
        if inscriptions.count() != 20 or students.count() != 20 or enrollments.count() != 20:
            raise CommandError("Le workflow inscription, etudiant et affectation ISMI est incomplet.")
        if payments.count() != expected_payments or payments.exclude(agent=payment_agent).exists():
            raise CommandError("Les paiements ISMI ne sont pas tous attribues a Mariam Cisse.")

    def _ensure_student_and_enrollment(self, inscription):
        result = create_student_after_first_payment(inscription)
        if not result or not result.get("student"):
            raise CommandError(f"Creation officielle de l'etudiant impossible pour inscription {inscription.pk}.")
        academic_result = result.get("academic_enrollment") or {}
        if academic_result.get("status") not in {"assigned", "already_assigned"}:
            raise CommandError(f"Affectation L1 impossible pour inscription {inscription.pk}.")
