# API des Composants Métier Partagés — ESFE Core

**Date :** 26 juillet 2026

---

## 1. Account Components

### account.profile_card

```python
ProfileCard.render(kwargs={
    "display_name": "Moussa Diarra",     # str, requis
    "avatar_url": "/media/avatar.jpg",   # str, optionnel
    "role": "Gestionnaire",              # str, optionnel
    "branch": "Bamako",                  # str, optionnel
    "status": "active",                  # str: active|suspended
    "status_label": "Actif",             # str, optionnel
    "profile_url": "/profile/",          # str, optionnel
    "compact": False,                    # bool, optionnel
})
```

### account.profile_dropdown

```python
ProfileDropdown.render(kwargs={
    "display_name": "Awa Koné",
    "avatar_url": "/media/avatar.jpg",
    "role": "Secrétaire",
    "profile_url": "/profile/",
    "edit_url": "/profile/edit/",
    "security_url": "/profile/security/",
    "preferences_url": "/profile/preferences/",
    "logout_url": "/logout/",
})
```

### account.profile_view

```python
ProfileView.render(kwargs={
    "display_name": "Fatoumata Koné",
    "email": "fatou@test.com",
    "role": "Secrétaire",
    "branch": "Sikasso",
    "phone": "+223 76 00 00 00",
    "address": "Bamako, Mali",
    "status": "active",
    "status_label": "Actif",
    "created_at": "janvier 2024",
    "last_seen": "il y a 2 heures",
    "bio": "Secrétaire principale",
    "extra_fields": [{"label": "Matricule", "value": "SEC-001"}],
    "actions": [{"label": "Modifier", "url": "/edit/", "icon": "pencil"}],
})
```

### account.profile_editor

```python
ProfileEditor.render(kwargs={
    "form": profile_form_instance,   # Django Form
    "hx_post": "/profile/edit/",
    "hx_target": "#profile-container",
    "title": "Modifier le profil",
})
```

### account.security_settings

```python
SecuritySettings.render(kwargs={
    "password_form": password_form_instance,
    "hx_post": "/profile/security/",
    "hx_target": "#security-container",
    "sessions": [{"device": "Chrome", "ip": "192.168.1.1", "is_current": True}],
})
```

### account.preference_settings

```python
PreferenceSettings.render(kwargs={
    "form": preference_form_instance,
    "hx_post": "/profile/preferences/",
    "hx_target": "#preferences-container",
})
```

---

## 2. Notification Components

### notifications.bell

```python
NotificationBell.render(kwargs={
    "unread_count": 5,
    "notifications_url": "/notifications/",
    "center_url": "/notifications/center/",
    "hx_get": "/notifications/widget/",
    "hx_target": "#notification-dropdown-content",
})
```

### notifications.badge

```python
NotificationBadge.render(kwargs={
    "count": 42,
    "max_count": 99,
    "size": "sm",  # sm|md|lg
})
```

### notifications.item

```python
NotificationItem.render(kwargs={
    "notification_id": "123",
    "title": "Nouvelle inscription",
    "summary": "Un étudiant a été inscrit en 6e A",
    "icon": "user-plus",
    "source": "Inscriptions",
    "time_ago": "il y a 5 min",
    "is_read": False,
    "priority": "normal",  # low|normal|high
    "action_url": "/inscriptions/123/",
    "hx_mark_read": "/notifications/read/123/",
})
```

### notifications.list

```python
NotificationList.render(kwargs={
    "notifications": [...],          # liste de dicts
    "empty_message": "Aucune notification",
    "empty_icon": "bell-off",
    "loading": False,
    "hx_load_more": "/notifications/page/2/",
    "mark_all_read_url": "/notifications/mark-all-read/",
})
```

### notifications.drawer

```python
NotificationDrawer.render(kwargs={
    "drawer_id": "notification-drawer",
    "title": "Notifications",
    "hx_load": "/notifications/widget/",
    "mark_all_read_url": "/notifications/mark-all-read/",
    "center_url": "/notifications/center/",
})
```

---

## 3. Student Components

### student.identity_card

```python
StudentIdentityCard.render(kwargs={
    "full_name": "Moussa Diakité",
    "matricule": "STU-2024-001",
    "photo_url": "/media/photos/moussa.jpg",
    "classe": "6e A",
    "niveau": "6ème",
    "filiere": "Sciences",
    "branch": "Bamako",
    "is_active": True,
    "detail_url": "/students/123/",
})
```

### student.status_card

```python
StudentStatusCard.render(kwargs={
    "status": "promoted",         # promoted|repeated|transferred|pending
    "status_label": "Promu",
    "decision_date": "15 juin 2026",
    "validation_academic": "Validé",
    "validation_finance": "En attente",
})
```

### student.progress_card

```python
StudentProgressCard.render(kwargs={
    "title": "Progression académique",
    "items": [
        {"label": "Mathématiques", "percentage": 75},
        {"label": "Français", "percentage": 45},
    ],
    "overall_percentage": 60,
    "overall_label": "Progression globale",
})
```

---

## 4. Shop Components

### shop.product_card

```python
ProductCard.render(kwargs={
    "product_id": "42",
    "name": "Blouse ESFE",
    "image_url": "/media/products/blouse.jpg",
    "category": "Uniforme",
    "price": "5 000 FCFA",
    "original_price": "7 500 FCFA",
    "stock": 12,
    "is_available": True,
    "variant_name": "Taille M",
    "action_url": "/shop/product/42/",
    "hx_post": "/shop/cart/add/42/",
})
```

### shop.product_grid

```python
ProductGrid.render(kwargs={
    "products": [...],              # liste de dicts
    "empty_message": "Aucun produit",
    "loading": False,
    "columns": 3,                   # 2|3|4
})
```

### shop.product_detail_drawer

```python
ProductDetailDrawer.render(kwargs={
    "drawer_id": "product-detail",
    "product": {
        "name": "Blouse ESFE",
        "image_url": "/media/products/blouse.jpg",
        "category": "Uniforme",
        "description": "Blouse officielle ESFE",
        "price": "5 000 FCFA",
        "stock": 12,
        "is_available": True,
        "variants": [{"name": "S", "extra_price": "0"}, {"name": "M", "extra_price": "0"}],
    },
    "hx_load": "/shop/product/42/detail/",
    "hx_add_to_cart": "/shop/cart/add/42/",
})
```

---

## 5. UI Core Enrichi

### ui_core.drawer (amélioré)

```python
Drawer.render(kwargs={
    "drawer_id": "my-drawer",
    "title": "Titre",
    "side": "right",           # left|right
    "size": "md",              # sm|md|lg|xl|full
    "has_form": True,          # active la confirmation avant abandon
    "content_url": "/load/content/",
})
```

### ui_core.form_field (amélioré)

```python
FormField.render(kwargs={
    "id": "my-field",
    "name": "field_name",
    "label": "Label",
    "type": "text",            # text|email|password|number|search|date|file|textarea|select
    "value": "valeur",
    "placeholder": "Placeholder",
    "help_text": "Aide",
    "error": "Erreur",
    "success": "Succès",
    "required": True,
    "disabled": False,
    "readonly": False,
    "loading": False,          # skeleton de chargement
    "prefix": "FCFA",
    "suffix": "/mois",
    "options": [{"value": "a", "label": "Option A"}],
})
```
