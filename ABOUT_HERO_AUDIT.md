# Audit About Hero

## Resume court

La page publique **A propos** est geree par l'app `core`.

L'image affichee dans le hero vient actuellement de :

```text
SiteConfiguration.about_hero_image
```

En base, la valeur actuelle est :

```text
site/about/hero/pexels-tima-miroshnichenko-5452210.jpg
```

Donc l'image rendue sur le site est :

```text
/media/site/about/hero/pexels-tima-miroshnichenko-5452210.jpg
```

## Route, vue et template

Route :

```python
path("apropos/", views.about, name="about")
```

Fichier :

```text
core/urls.py
```

Vue :

```text
core/views.py
def about(request)
```

Template principal :

```text
core/templates/core/about.html
```

Composant utilise pour le hero :

```text
ui/components/about/about_hero.py
ui/templates/about/about_hero.html
```

## Priorite de l'image

Dans `core/templates/core/about.html`, le systeme fait ceci :

1. Si `site_configuration.about_hero_image` existe, il l'utilise.
2. Sinon, il utilise `presentation.hero_image`.
3. Sinon, le composant tente un fallback statique : `static("images/hero-default.jpg")`.

Important : le fallback `static/images/hero-default.jpg` semble absent du projet.

## Modeles concernes

Modele prioritaire :

```text
core.models.SiteConfiguration
```

Champ prioritaire :

```python
about_hero_image = models.ImageField(
    upload_to="site/about/hero/",
    blank=True,
    null=True,
    verbose_name="Image Hero (A propos)"
)
```

Modele secondaire :

```text
core.models.InstitutionPresentation
```

Champ secondaire :

```python
hero_image = models.ImageField(
    upload_to="institution/hero/",
    blank=True,
    null=True,
    verbose_name="Image Hero (background)"
)
```

## Pourquoi l'image n'apparait pas dans le SuperAdmin personnalise

Le probleme vient de `/superadmin/settings/`.

Cette page ne modifie que le modele :

```text
Institution
```

Elle ne charge pas :

```text
SiteConfiguration
InstitutionPresentation
```

Elle n'a pas non plus :

```html
enctype="multipart/form-data"
```

Donc elle ne peut pas uploader d'image.

Fichiers concernes :

```text
superadmin/views.py
superadmin/templates/superadmin/settings/index.html
```

## Ou modifier l'image maintenant

Le systeme existe deja dans le Django Admin natif :

```text
/admin/
```

Chercher :

```text
Core > Configuration du site
```

Puis modifier :

```text
Image Hero (A propos)
```

Ce champ correspond a :

```text
SiteConfiguration.about_hero_image
```

## Probleme reel

Le systeme est deja present, mais il est mal expose.

Le Django Admin natif permet de modifier l'image, mais le SuperAdmin personnalise ne le permet pas encore.

## Recommandation

Ajouter dans le SuperAdmin personnalise une section dediee :

```text
SuperAdmin > Parametres > Site public > Page A propos
```

Elle devrait gerer :

- upload de `about_hero_image`
- apercu de l'image actuelle
- remplacement de l'image
- suppression de l'image
- fallback propre
- validation du format et de la taille
- textes hero : titre, sous-titre, CTA

## Conclusion

L'image du hero About actuellement affichee est configuree dans :

```text
SiteConfiguration.about_hero_image
```

Elle est accessible dans le Django Admin natif, mais pas encore dans le SuperAdmin personnalise.

Il faut donc brancher `SiteConfiguration` dans `/superadmin/settings/` ou creer une vraie page SuperAdmin pour la configuration du site public.
