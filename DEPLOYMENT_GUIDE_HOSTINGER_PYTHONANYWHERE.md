# Déploiement ESFE — Hostinger VPS & PythonAnywhere

Ce document prépare le projet `esfe` pour deux cibles :
- **Hostinger VPS** : cible recommandée pour la production finale
- **PythonAnywhere** : cible de démonstration / prévalidation rapide

---

## 1. Pré-requis communs

### Variables d’environnement minimales

Créer un fichier `.env` sur le serveur à partir de `.env.example` avec au minimum :

```env
SECRET_KEY=une-cle-secrete-forte
DEBUG=False
ALLOWED_HOSTS=esfe-domaine.com,www.esfe-domaine.com,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://esfe-domaine.com,https://www.esfe-domaine.com
BASE_URL=https://www.esfe-domaine.com

DB_NAME=esfe_db
DB_USER=esfe_user
DB_PASSWORD=mot-de-passe-fort
DB_HOST=127.0.0.1
DB_PORT=5432

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=adresse@example.com
EMAIL_HOST_PASSWORD=mot-de-passe-ou-app-password
DEFAULT_FROM_EMAIL=noreply@esfe-mali.org

ENABLE_BROWSER_RELOAD=False
ENABLE_WEBSOCKETS=True
REDIS_URL=redis://127.0.0.1:6379/1
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
USE_X_FORWARDED_HOST=True
FFMPEG_PATH=ffmpeg
```

### Commandes Django à exécuter après chaque déploiement

```powershell
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

### Build CSS production

```powershell
npm install
npm run build:css
```

---

## 2. Déploiement Hostinger VPS (production finale)

## Recommandation
Hostinger VPS est la **meilleure cible de production** pour ce projet, car il permet de gérer :
- Django complet
- PostgreSQL
- Redis
- ASGI / WebSockets
- Reverse proxy Nginx
- HTTPS

## Stack recommandée
- Python 3.12+ ou 3.13+
- PostgreSQL
- Redis
- Nginx
- Supervisor ou systemd
- Uvicorn pour ASGI

## Étapes serveur

### 1) Installer les paquets système
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv nginx redis-server postgresql postgresql-contrib ffmpeg git
```

### 2) Cloner le dépôt
```bash
git clone https://github.com/pixamac-ml/esfe-core.git
cd esfe-core
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
npm install
npm run build:css
```

### 3) Configurer la base PostgreSQL
Créer la base, l’utilisateur et appliquer les droits.

### 4) Placer le `.env`
Copier les variables de production dans un fichier `.env` à la racine du projet.

### 5) Préparer Django
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

### 6) Service Uvicorn / ASGI
Exemple `systemd` :

```ini
[Unit]
Description=ESFE Uvicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/esfe-core
Environment="PATH=/var/www/esfe-core/.venv/bin"
ExecStart=/var/www/esfe-core/.venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

### 7) Reverse proxy Nginx
- `/static/` -> `staticfiles/`
- `/media/` -> `media/`
- proxy pass vers `127.0.0.1:8000`
- certificat SSL Let’s Encrypt

---

## 3. Déploiement PythonAnywhere (démo / validation)

## Recommandation
PythonAnywhere est adapté pour une **version de démonstration** rapide.

## Limite importante
Pour PythonAnywhere, le plus simple est d’utiliser le projet en **mode WSGI** sans dépendre fortement des WebSockets.

Utiliser dans le `.env` :

```env
DEBUG=False
ENABLE_BROWSER_RELOAD=False
ENABLE_WEBSOCKETS=False
```

## Étapes

### 1) Cloner le dépôt
Dans une console Bash PythonAnywhere :

```bash
git clone https://github.com/pixamac-ml/esfe-core.git
cd esfe-core
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
npm install
npm run build:css
```

### 2) Configurer le `.env`
- `DEBUG=False`
- `ALLOWED_HOSTS=votre-login.pythonanywhere.com`
- `CSRF_TRUSTED_ORIGINS=https://votre-login.pythonanywhere.com`
- `ENABLE_WEBSOCKETS=False`

### 3) Configurer le Web app dashboard PythonAnywhere
- Source code : racine du projet
- Virtualenv : `.venv`
- WSGI file : faire pointer vers `config.wsgi`

### 4) Mapping static / media
- URL `/static/` -> dossier `staticfiles`
- URL `/media/` -> dossier `media`

### 5) Finaliser
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Puis recharger l’application depuis le dashboard PythonAnywhere.

---

## 4. Différence clé entre les deux plateformes

### Hostinger VPS
- idéal pour la vraie production
- compatible ASGI + Redis + WebSockets
- contrôle total du serveur

### PythonAnywhere
- idéal pour démo et revue métier
- plus simple à publier vite
- préférable en **WSGI**, sans WebSockets actifs

---

## 5. Ordre conseillé pour toi maintenant

1. **PythonAnywhere** pour la présentation publique rapide
2. **Hostinger VPS** pour la vraie mise en production
3. Basculer le domaine final sur Hostinger après validation

---

## 6. Checklist finale avant ouverture publique

- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` correct
- [ ] `CSRF_TRUSTED_ORIGINS` correct
- [ ] `.env` présent sur le serveur
- [ ] `python manage.py migrate`
- [ ] `python manage.py collectstatic --noinput`
- [ ] `npm run build:css`
- [ ] pages légales publiées
- [ ] consentement cookies visible
- [ ] formulaires email testés
- [ ] médias accessibles
- [ ] HTTPS actif
- [ ] superadmin accessible uniquement aux bons comptes

---

## 7. Commandes de démarrage utiles

### Dév local
```powershell
python manage.py runserver
npm run watch:css
```

### Validation production locale
```powershell
$env:DEBUG='False'
python manage.py check --deploy
python manage.py collectstatic --noinput
```

