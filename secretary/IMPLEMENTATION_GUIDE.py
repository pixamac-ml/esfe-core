# ════════════════════════════════════════════════════════════════════
#  GUIDE D'IMPLÉMENTATION — Dashboard Secrétaire v2
#  À lire avant de toucher au code
# ════════════════════════════════════════════════════════════════════

"""
FICHIERS FOURNIS
────────────────
1. secretary_dashboard.html          → remplace secretary/templates/secretary/dashboard.html
2. secretary_partials__flux_block.html → nouveau partial : secretary/templates/secretary/partials/_flux_block.html
3. secretary_services_additions.py   → ajouts à intégrer dans secretary/services.py
4. Ce guide

════════════════════════════════════════════════════════════════════
ÉTAPE 1 — Copier les templates
════════════════════════════════════════════════════════════════════

  cp secretary_dashboard.html \
     <ton_projet>/secretary/templates/secretary/dashboard.html

  cp secretary_partials__flux_block.html \
     <ton_projet>/secretary/templates/secretary/partials/_flux_block.html


════════════════════════════════════════════════════════════════════
ÉTAPE 2 — Mettre à jour secretary/services.py
════════════════════════════════════════════════════════════════════

  a) Ajouter en bas du fichier les 4 nouvelles fonctions :
       get_academic_results()
       get_pending_shop_orders()
       get_quick_actions()
       get_nav_links()

  b) Remplacer l'ancienne get_secretary_dashboard_data() par la nouvelle.

  c) Ajouter les imports manquants en haut du fichier :
       from news.models import ResultSession        # si pas déjà présent
       from shop.models import ShopOrder            # si pas déjà présent


════════════════════════════════════════════════════════════════════
ÉTAPE 3 — Vérifier que ResultSession a bien is_published
════════════════════════════════════════════════════════════════════

  Dans news/models.py, ResultSession doit avoir :
    is_published = models.BooleanField(default=False)
    fichier_pdf  = models.FileField(...)
    filiere      = models.CharField(...)
    classe       = models.CharField(...)
    annee_academique = models.CharField(...)
    titre        = models.CharField(...)
    annexe       = models.CharField(...)

  → La seed seed_results.py confirme que c'est bien le cas ✓


════════════════════════════════════════════════════════════════════
ÉTAPE 4 — Vérifier les URLs nécessaires
════════════════════════════════════════════════════════════════════

  URLs existantes utilisées (toutes dans secretary/urls.py) :
    secretary:visitor_create
    secretary:appointment_create
    secretary:document_receipt_create
    secretary:registry_create
    secretary:task_create
    secretary:registry_start / registry_mark_processed / registry_archive
    secretary:document_receipt_start / document_receipt_archive
    secretary:appointment_complete
    secretary:visitor_complete
    secretary:task_start / task_complete
    secretary:htmx_student_results
    secretary:htmx_messages_panel
    secretary:student_snapshot

  URLs nouvelles à vérifier/créer dans shop/urls.py :
    shop:order_list
    shop:order_detail  (pk)
    shop:deliver_order  (pk, POST)  ← action de livraison secrétaire

  Si deliver_order n'existe pas encore → voir ÉTAPE 5.


════════════════════════════════════════════════════════════════════
ÉTAPE 5 — Action de livraison shop (secrétaire seulement)
════════════════════════════════════════════════════════════════════

  Dans shop/views.py, ajouter :

    @login_required
    def deliver_order(request, pk):
        \"\"\"Secrétaire marque une commande 'ready' comme remise.\"\"\"
        from secretary.permissions import ensure_secretary_access
        ensure_secretary_access(request.user)

        order = get_object_or_404(ShopOrder, pk=pk, status=ShopOrder.STATUS_READY)
        if request.method == "POST":
            order.status = ShopOrder.STATUS_DELIVERED
            order.delivered_by = request.user
            order.delivered_at = timezone.now()
            order.save(update_fields=["status", "delivered_by", "delivered_at", "updated_at"])
            messages.success(request, f"Commande {order.reference} remise à l'étudiant.")
        return redirect("shop:order_list")

  Dans shop/urls.py, ajouter :
    path("orders/<int:pk>/deliver/", deliver_order, name="deliver_order"),


════════════════════════════════════════════════════════════════════
ÉTAPE 6 — Résultats : droits lecture seule (sécurité)
════════════════════════════════════════════════════════════════════

  La vue secretary_dashboard passe `academic_results` uniquement en contexte.
  Aucune form, aucun POST lié aux résultats depuis ce module.
  Seul le lien PDF pointe vers le fichier existant (lecture).

  Pour renforcer : dans news/views.py, la vue qui sert les PDF
  doit vérifier l'authentification (déjà géré si MEDIA_ROOT protégé
  ou si vous utilisez X-Accel-Redirect/whitenoise).

  La secrétaire NE PEUT PAS :
    ✗ Créer / modifier / supprimer un ResultSession
    ✗ Changer is_published
    ✗ Uploader un PDF
  Ces actions restent réservées à l'admin Django ou aux roles enseignant/admin.


════════════════════════════════════════════════════════════════════
RÉCAPITULATIF DES SECTIONS DU NOUVEAU DASHBOARD
════════════════════════════════════════════════════════════════════

  §1  Header KPI         — date live + 5 compteurs en ligne + 3 boutons rapides
  §2  Flux du jour       — 5 sous-blocs (registre / docs / RDV / visites / tâches)
                           → 1 row par item, actions inline compactes
  §3  Résultats          — tableau lecture seule, filtre JS côté client
                           → téléchargement PDF direct
  §4  Dossiers étudiants — recherche HTMX live, snapshot modal, bouton "+ Registre"
  §5  Commandes shop     — pending_payment + ready, action "Remettre" sur ready
  §6  Actions rapides    — grille 2×3, modal HTMX sans navigation
  §7  Messages/Notifs    — 6 dernières notifications + bouton "tout voir"
  §8  Navigation         — liens vers les listes avec compteurs
"""
