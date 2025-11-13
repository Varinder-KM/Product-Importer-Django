# 🛍️ Product Importer — Django

A Django-based project for importing and managing product data.  
This project provides tools to import products via scripts, webhooks, and admin UI.  
It includes reusable modules, templates, and webhook handlers for flexible integration.

---

## 📑 Table of Contents

- [Features](#-features)
- [Repository Structure](#-repository-structure)
- [Requirements](#-requirements)
- [Quick Start (Development)](#-quick-start-development)
- [Environment Variables](#-environment-variables)
- [Usage](#-usage)
- [Development Notes](#-development-notes)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [License & Contact](#-license--contact)

---

## 🚀 Features

- Built with **Django** for scalability and modularity.
- **Product import system** via admin, webhook, or standalone scripts.
- Organized code with dedicated folders for `scripts`, `templates`, and `webhooks`.
- Supports **customizable import logic** and external integrations.
- Environment configuration with `.env` for secure settings.

---

## 🗂 Repository Structure

Product-Importer-Django/
─ config/ # Django project settings & wsgi/asgi
─ products/ # Main app: models, admin, views
─ scripts/ # Helper and import scripts
─ templates/ # HTML templates for UI
─ webhooks/ # Webhook event handlers
─ dev-instructions.md # Developer setup notes
─ .env.example # Example environment variables
─ requirements.txt # Project dependencies
─ manage.py # Django management script


## ⚙️ Requirements

- Python 3.10+  
- pip  
- Django (installed via `requirements.txt`)

Install dependencies using:

`pip install -r requirements.txt`


## 🚀 Quick Start (Development)
1. Clone the Repository
   
`git clone https://github.com/Varinder-KM/Product-Importer-Django.git`

`cd Product-Importer-Django`

2. Create and Activate Virtual Environment
`python -m venv .venv`

#### Windows
`.venv\Scripts\activate`

#### macOS / Linux
`source .venv/bin/activate`

3. Install Dependencies
`pip install -r requirements.txt`

4. Set Up Environment Variables

Create a .env file from the example:

`cp .env.example .env`


Then edit .env to add your:

`SECRET_KEY`

`DATABASE_URL or individual DB configs`

Any API keys or webhook secrets

5. Apply Migrations
`python manage.py migrate`

6. Create Superuser
`python manage.py createsuperuser`

7. Run the Development Server
`python manage.py runserver`


Access the app at:
👉` http://127.0.0.1:8000/`

Login to the Django admin to manage or import products.


## 🌐 Environment Variables

The `.env.example` file contains placeholders for required configuration.

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DATABASE_URL` | Connection string for your database |
| `DEBUG` | Set to `True` for local development |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts |
| `WEBHOOK_SECRET` | (Optional) Secret for webhook verification |


## 📦 Usage

You can import products in several ways:

### 🔹 1. Using Django Admin
Add or bulk-import product data directly from the Django admin interface.

### 🔹 2. Using Scripts
Navigate to the `scripts/` folder and run available scripts.

Example (if you have a CSV import script):
`python manage.py runscript import_products`

### 🔹 3. Using Webhooks
The `webhooks/` module handles external product update events. Send HTTP POST requests to the configured webhook endpoint to trigger product creation or updates.
