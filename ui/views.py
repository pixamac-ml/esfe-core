from django.shortcuts import render


def gallery(request):
    ctx = {
        # --- Avatar group ---
        "avatars_demo": [
            {"initials": "JD"}, {"initials": "AK"},
            {"initials": "ML"}, {"initials": "SB"}, {"initials": "TR"},
        ],
        # --- KPI row ---
        "kpi_cards": [
            {"label": "Étudiants", "value": "1 234", "icon": "users"},
            {"label": "Enseignants", "value": "89", "icon": "graduation-cap"},
            {"label": "Classes", "value": "24", "icon": "school"},
            {"label": "Taux réussite", "value": "94%", "icon": "award"},
        ],
        # --- DataTable ---
        "table_headers": [
            {"label": "Nom"},
            {"label": "Prénom"},
            {"label": "Classe", "sortable": True, "sort_url": "?sort=classe"},
            {"label": "Moyenne", "sortable": True, "sort_url": "?sort=moyenne", "sorted": True, "sort_dir": "desc"},
        ],
        "table_rows": [
            {"id": 1, "cells": [{"value": "Diakité"}, {"value": "Moussa"}, {"value": "6e A"}, {"value": "14,5", "editable": True, "field": "note"}]},
            {"id": 2, "cells": [{"value": "Traoré"}, {"value": "Aminata"}, {"value": "5e B"}, {"value": "16,2", "editable": True, "field": "note"}]},
            {"id": 3, "cells": [{"value": "Keita"}, {"value": "Souleymane"}, {"value": "4e C"}, {"value": "12,8", "editable": True, "field": "note"}]},
        ],
        "empty_rows": [],
        # --- Select ---
        "classe_options": [
            {"value": "6e", "label": "6e"},
            {"value": "5e", "label": "5e"},
            {"value": "4e", "label": "4e"},
        ],
        # --- Combobox ---
        "city_options": [
            {"value": "bko", "label": "Bamako"},
            {"value": "bke", "label": "Burkina"},
            {"value": "abj", "label": "Abidjan"},
        ],
        # --- Radio ---
        "genre_options": [
            {"value": "M", "label": "Masculin"},
            {"value": "F", "label": "Féminin"},
        ],
        # --- FilterBar ---
        "filter_options": [
            {
                "name": "classe", "placeholder": "Classe",
                "options": [{"value": "6e", "label": "6e"}, {"value": "5e", "label": "5e"}],
            },
            {
                "name": "statut", "placeholder": "Statut",
                "options": [{"value": "actif", "label": "Actif"}, {"value": "inactif", "label": "Inactif"}],
            },
        ],
        # --- Breadcrumb ---
        "breadcrumb_items": [
            {"label": "Dashboard", "url": "/"},
            {"label": "Gestion"},
            {"label": "Étudiants"},
        ],
        # --- Tabs ---
        "tab_items": [
            {"id": "infos", "label": "Informations", "icon": "info"},
            {"id": "notes", "label": "Notes", "icon": "file-text"},
            {"id": "paiements", "label": "Paiements", "icon": "wallet"},
        ],
        # --- Stepper ---
        "step_items": [
            {"label": "Inscription"},
            {"label": "Documents"},
            {"label": "Paiement"},
            {"label": "Confirmation"},
        ],
        "vertical_step_items": [
            {"label": "Création dossier", "description": "Remplir le formulaire en ligne", "icon": "file-text"},
            {"label": "Validation documents", "description": "Fournir les pièces justificatives", "icon": "folder-check"},
            {"label": "Paiement frais", "description": "Régler les frais de scolarité", "icon": "wallet"},
            {"label": "Inscription finalisée", "description": "Confirmation et accès plateforme", "icon": "graduation-cap"},
        ],
        # --- Timeline ---
        "timeline_items": [
            {"title": "Inscription", "description": "Moussa Diakité inscrit en 6e A", "date": "12 juin", "tone": "primary", "icon": "user-plus"},
            {"title": "Paiement", "description": "Frais de scolarité 2025-2026 réglés", "date": "12 juin", "tone": "success", "icon": "wallet"},
            {"title": "Alerte", "description": "Absence non justifiée signalée", "date": "11 juin", "tone": "danger", "icon": "alert-triangle"},
        ],
        # --- Dropdown items ---
        "dropdown_items": [
            {"label": "Voir", "icon": "eye", "url": "#"},
            {"label": "Modifier", "icon": "pencil", "url": "#"},
            {"label": "Supprimer", "icon": "trash-2", "url": "#", "danger": True, "divider": True},
        ],
        # --- Cell demo data ---
        "status_cell_items": [
            {"label": "Payé", "tone": "success", "icon": "check-circle"},
            {"label": "En attente", "tone": "warning", "icon": "clock"},
            {"label": "En retard", "tone": "danger", "icon": "alert-circle"},
            {"label": "Inscrit", "tone": "primary", "icon": "user-check"},
            {"label": "Brouillon", "tone": "neutral"},
        ],
        # --- Schedule demo ---
        "schedule_slots": [
            {"day": 0, "start": 1, "end": 3, "label": "Mathématiques", "teacher": "M. Koné", "room": "101", "color": "school-primary"},
            {"day": 0, "start": 4, "end": 5, "label": "Physique", "teacher": "Mme Diallo", "room": "103", "color": "success"},
            {"day": 1, "start": 2, "end": 4, "label": "Français", "teacher": "M. Traoré", "room": "102", "color": "info"},
            {"day": 1, "start": 5, "end": 6, "label": "Anglais", "teacher": "Mme Sanogo", "room": "201", "color": "warning"},
            {"day": 2, "start": 0, "end": 2, "label": "Histoire", "teacher": "M. Camara", "room": "104", "color": "school-primary"},
            {"day": 2, "start": 3, "end": 5, "label": "SV.Terre", "teacher": "Mme Keita", "room": "105", "color": "success"},
            {"day": 3, "start": 1, "end": 2, "label": "Anglais", "teacher": "Mme Sanogo", "room": "201", "color": "warning"},
            {"day": 3, "start": 4, "end": 6, "label": "Mathématiques", "teacher": "M. Koné", "room": "101", "color": "school-primary"},
            {"day": 4, "start": 2, "end": 4, "label": "EPS", "teacher": "M. Diarra", "room": "Stade", "color": "info"},
            {"day": 4, "start": 5, "end": 7, "label": "Physique", "teacher": "Mme Diallo", "room": "103", "color": "success"},
        ],
        "actions_cell_demo": [
            {"icon": "eye", "url": "#", "title": "Voir"},
            {"divider": True},
            {"icon": "pencil", "url": "#", "title": "Modifier"},
            {"icon": "trash-2", "url": "#", "title": "Supprimer"},
        ],
    }
    return render(request, "ui/gallery.html", ctx)
