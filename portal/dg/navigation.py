"""Navigation métier du cockpit de Direction générale.

L'URL reste la source de vérité : ``domain`` décrit le grand domaine et
``section`` la sous-section effectivement rendue.  Les anciens liens ne
contenant que ``section`` restent valides grâce au domaine déduit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DgDomain:
    key: str
    label: str
    icon: str
    default_section: str
    sections: tuple[tuple[str, str, str], ...]


DG_DOMAINS: tuple[DgDomain, ...] = (
    DgDomain(
        "commandement",
        "Commandement",
        "layout-dashboard",
        "overview",
        (("overview", "Vue d’ensemble", "layout-dashboard"),),
    ),
    DgDomain(
        "annexes",
        "Annexes",
        "building-2",
        "branch_list",
        (
            ("annexes", "Vue d’ensemble", "building-2"),
            ("branch_list", "Liste des annexes", "list"),
            ("branch_comparison", "Comparaison", "chart-no-axes-combined"),
            ("branch_managers", "Responsables", "user-round-check"),
            ("branch_activity", "Activité", "activity"),
            ("alerts", "Alertes", "triangle-alert"),
        ),
    ),
    DgDomain(
        "finance",
        "Finance",
        "hand-coins",
        "finance",
        (
            ("finance", "Synthèse", "wallet-cards"),
            ("payments", "Encaissements", "circle-dollar-sign"),
            ("expenses", "Dépenses", "receipt-text"),
            ("receivables", "Créances", "badge-euro"),
            ("cash_movements", "Caisses", "landmark"),
            ("closures", "Clôtures", "calendar-check-2"),
            ("bank_transfers", "Versements", "landmark"),
            ("finance_reports", "Rapports", "file-bar-chart-2"),
            ("coupons", "Coupons", "ticket-percent"),
        ),
    ),
    DgDomain(
        "academique",
        "Académique",
        "graduation-cap",
        "schedule",
        (
            ("academic_overview", "Vue d’ensemble", "graduation-cap"),
            ("formations", "Catalogue des formations", "book-open-check"),
            ("academic_calendar", "Calendrier académique", "calendar-range"),
            ("classes", "Classes", "school"),
            ("schedule", "Planning", "calendar-days"),
            ("evaluations", "Évaluations", "clipboard-check"),
            ("results", "Résultats", "chart-column"),
            ("progression", "Progression", "trending-up"),
            ("diplomas", "Diplômes", "award"),
        ),
    ),
    DgDomain(
        "etudiants",
        "Étudiants",
        "users-round",
        "workflows",
        (
            ("students_overview", "Vue d’ensemble", "users-round"),
            ("students", "Étudiants", "contact-round"),
            ("enrollments", "Inscriptions", "file-check-2"),
            ("reenrollments", "Réinscriptions", "refresh-cw"),
            ("workflows", "Passages / promotions", "git-compare-arrows"),
            ("student_cases", "Situations particulières", "shield-alert"),
        ),
    ),
    DgDomain(
        "personnel",
        "Personnel",
        "users",
        "rh",
        (
            ("staff_overview", "Vue d’ensemble", "users"),
            ("rh", "Personnel", "contact-round"),
            ("recruitment", "Recrutements", "user-plus"),
            ("assignments", "Affectations", "network"),
            ("staff_contracts", "Contrats / statuts", "file-badge"),
            ("staff_access", "Accès", "key-round"),
            ("staff_history", "Historique", "history"),
        ),
    ),
    DgDomain(
        "gouvernance",
        "Gouvernance",
        "landmark",
        "analytics",
        (
            ("documents", "Documents & décisions", "files"),
            ("analytics", "Analyses & rapports", "chart-no-axes-combined"),
            ("realtime", "Activité récente", "activity"),
            ("audit", "Audit & contrôle", "shield-check"),
            ("exports", "Exports", "file-down"),
        ),
    ),
    DgDomain(
        "mon_espace",
        "Mon espace",
        "circle-user-round",
        "messaging",
        (
            ("messaging", "Messagerie", "messages-square"),
            ("settings", "Profil et paramètres", "settings"),
        ),
    ),
)

DG_SIDEBAR_GROUPS = (
    ("Commandement", ("commandement",)),
    ("Pilotage institutionnel", ("annexes", "finance", "academique", "etudiants", "personnel")),
    ("Gouvernance", ("gouvernance",)),
    ("Mon espace", ("mon_espace",)),
)

DG_DOMAINS_BY_KEY = {domain.key: domain for domain in DG_DOMAINS}
DG_SECTION_TO_DOMAIN = {
    section: domain.key
    for domain in DG_DOMAINS
    for section, _label, _icon in domain.sections
}
DG_SECTIONS = frozenset(DG_SECTION_TO_DOMAIN)


def resolve_dg_navigation(raw_domain: str | None, raw_section: str | None) -> tuple[DgDomain, str]:
    """Return a valid domain/section pair without trusting query values."""

    requested_section = str(raw_section or "").strip().lower()
    requested_domain = str(raw_domain or "").strip().lower()
    # Compatibility with URLs generated before Governance grouped the two
    # existing reporting/activity workspaces under one executive domain.
    requested_domain = {"analyses": "gouvernance"}.get(requested_domain, requested_domain)

    if requested_section in DG_SECTION_TO_DOMAIN:
        domain = DG_DOMAINS_BY_KEY[DG_SECTION_TO_DOMAIN[requested_section]]
        return domain, requested_section

    domain = DG_DOMAINS_BY_KEY.get(requested_domain)
    if domain is not None:
        return domain, domain.default_section

    domain = DG_DOMAINS_BY_KEY["commandement"]
    return domain, domain.default_section


def domain_for_section(section: str) -> DgDomain:
    """Resolve a section defensively for server-side and template callers."""

    return DG_DOMAINS_BY_KEY[DG_SECTION_TO_DOMAIN.get(section, "commandement")]
