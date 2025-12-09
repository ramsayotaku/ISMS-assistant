
# <img src="https://via.placeholder.com/800x180.png?text=ISO+27001+AI+Policy+Generator" width="100%">

# ISO 27001 AI Policy Generator

A Django + OpenAI powered system that generates, validates, and manages ISO/IEC 27001:2022 security policies using Large Language Models.
This tool automates Annex A policy drafting, performs structural and control-based validation, and supports batch generation and internal ISMS workflows.

---

## About This Project

The ISO 27001 AI Policy Generator is a full-stack solution designed for cybersecurity professionals, ISMS managers, compliance teams, and researchers.
It automates the creation of ISO 27001:2022–aligned documentation using generative AI and enriches outputs with:

* Company-specific context
* Annex A control mapping
* Policy-specific validation rules
* Keyword-based and structural completeness checks
* Markdown-to-HTML rendering
* Editable policies & version-ready storage

The goal is to reduce manual effort in writing and reviewing security policies while maintaining audit-friendly quality.

---

## Key Features

* **AI-powered ISO 27001 policy generation** using OpenAI GPT-4o-mini
* **Annex A control mapping** (Excel import supported)
* **Company-specific context injection** into prompts
* **Batch generation** — generate full ISMS documentation at once
* **Markdown rendering with sanitization**
* **Validation Engine**:

  * Required policy sections
  * Control keyword matching
  * Policy-specific rule evaluation
  * Readability metrics
* **Policy History & Editing**
* **Login & Authentication**
* **OpenAI API v1 compatible client**

---

## Screenshots

> Add your screenshots here once UI is ready.

Example placeholders:

### Dashboard

<img src="https://via.placeholder.com/900x450.png?text=Dashboard+Screenshot" width="650">

### Policy Generation

<img src="https://via.placeholder.com/900x450.png?text=Policy+Generation+Form" width="650">

### Validation Output

<img src="https://via.placeholder.com/900x450.png?text=Validation+Results" width="650">

---

## Installation

### Requirements

* Python 3.11+
* Django 5.x
* OpenAI Python SDK ≥ 1.0
* SQLite (default) or PostgreSQL

---

## Setup

Clone the repository:

```bash
git clone https://github.com/yourusername/iso27001-ai-policy-generator.git
cd iso27001-ai-policy-generator
```

Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate     # macOS/Linux
venv\Scripts\activate        # Windows
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file:

```
DEBUG=True
SECRET_KEY=your-secret-key

# OpenAI
OPENAI_API_KEY=your-openai-api-key
OPENAI_DEFAULT_MODEL=gpt-4o-mini
```

---

## Database Setup

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

---

## Running the Application

Start the development server:

```bash
python manage.py runserver
```

Open:

```
http://127.0.0.1:8000/
```

---

## Import Annex A Mapping (Excel)

Load your mapping file:

```bash
python manage.py import_mapping /path/to/ISO27001_Document_Mapping.xlsx
```

Supported control formats:

* `A.6.1 – A.6.4`
* `A.8.24, A.8.25`
* `A.8.24 — Secure Coding`

---

## How It Works

### 1. AI Policy Generation

Policies are generated using structured prompts containing:

* Selected PolicyTemplate
* Annex A controls
* Organization context
* PromptTemplate text

### 2. Validation Engine

Evaluates generated policy against:

* Required ISO sections
* Control keyword sets
* Policy-specific rule sets
* Readability metrics

Results stored in `ValidationResult`.

### 3. Markdown Rendering

Policies written in Markdown are rendered as HTML through a custom Django filter that safely sanitizes output.

---

## Directory Overview

```
generator/
│
├── models.py              # Data models
├── forms.py               # Forms for generation/editing
├── views.py               # Class-based views
├── services/
│   ├── openai_client.py   # Patched OpenAI v1+ client
│   ├── validator.py       # Validation engine
│   └── rule_engine.py     # Policy-specific rule handler (optional)
├── templates/generator/   # UI templates
├── templatetags/
│   └── markdown_extras.py # Safe markdown → HTML renderer
└── management/commands/
    └── import_mapping.py  # Excel-based Annex A control importer
```

---

## Troubleshooting

### OpenAI ChatCompletion Error

Use the v1 API (`OpenAI()`), not deprecated `ChatCompletion`.

### Markdown Not Rendering

Ensure:

```django
{% load markdown_extras %}
{{ policy.generated_text|markdown_to_html }}
```

Install:

```bash
pip install markdown bleach
```

### JSON Serialization Errors

Handled by patched OpenAI client with `.to_dict()` fallback.

---

## Future Enhancements

* Semantic validation (embedding-based)
* Versioning + diff viewer
* Multi-model support (Gemini, Claude, HF)
* Export controls → policy traceability matrix
* PDF/DOCX export modules

---

## Academic Context

Developed as part of an MSc Cybersecurity thesis:

**"Evaluating the Effectiveness of Generative AI for ISO/IEC 27001:2022 Policy Automation"**

---

## License

MIT License (or choose your own)

---
