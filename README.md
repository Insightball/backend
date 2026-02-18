# INSIGHTBALL - Backend

API FastAPI pour la plateforme INSIGHTBALL.

## 🚀 Installation

### Prérequis

- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### Setup

```bash
# Crée un environnement virtuel
python3 -m venv venv

# Active l'environnement
source venv/bin/activate  # Mac/Linux
# ou
venv\Scripts\activate  # Windows

# Installe les dépendances
pip install -r requirements.txt

# Copie le fichier d'environnement
cp .env.example .env

# Édite .env avec tes vraies valeurs
nano .env

# Lance le serveur
python main.py
```

Le serveur démarre sur http://localhost:8000

## 📦 Technologies

- **FastAPI** - Framework API moderne
- **SQLAlchemy** - ORM
- **PostgreSQL** - Database
- **Celery** - Queue processing
- **Redis** - Cache + Queue
- **Stripe** - Paiements
- **boto3** - AWS S3

## 🏗️ Structure

```
app/
├── models/         # Database models
├── schemas/        # Pydantic schemas
├── routes/         # API endpoints
├── services/       # Business logic
├── tasks/          # Celery tasks (IA processing)
├── utils/          # Utilities
└── config.py       # Configuration
```

## 🔧 Scripts

```bash
# Développement
python main.py

# Tests
pytest

# Migrations database
alembic revision --autogenerate -m "description"
alembic upgrade head

# Celery worker (processing IA)
celery -A app.tasks worker --loglevel=info
```

## 📝 API Documentation

Une fois le serveur lancé :

- Swagger UI : http://localhost:8000/docs
- ReDoc : http://localhost:8000/redoc

## 🗄️ Database Setup

```bash
# Crée la database PostgreSQL
createdb insightball

# Lance les migrations
alembic upgrade head
```

## 🔐 Variables d'environnement

Voir `.env.example` pour la liste complète.

Critiques :
- `DATABASE_URL` - Connexion PostgreSQL
- `SECRET_KEY` - JWT signing
- `STRIPE_SECRET_KEY` - Paiements
- `AWS_ACCESS_KEY_ID` - Upload S3

## 👨‍💻 Développement

Code par Claude + Tchitcha
Version 1.0 - Février 2026
