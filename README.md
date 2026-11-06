# TradeNexa AI – Smart Import & Export Management System

A runnable Flask + SQLite academic demonstration. It includes account registration/login, an indicative keyword-based product classification demo, an import/export cost estimator, sample market suggestions, draft PDF document generation, manual shipment records, a trade Q&A assistant, and analytics.

## Important limitations
- HS code results are indicative demo suggestions, not official classifications.
- Market suggestions are illustrative and are not based on live trade statistics.
- Customs rates must be verified and entered by the user.
- Shipment status is manually entered; no live carrier tracking is connected.
- The chatbot uses a deterministic fallback and does not claim to be a live AI model.
- Generated documents are drafts. Review them with a qualified trade professional before use.

## Requirements
- Python 3.10+
- VS Code or another code editor

## Run on Windows
1. Extract the ZIP.
2. Open the extracted `TradeNexa_AI` folder in VS Code.
3. Open Terminal in VS Code.
4. Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\\Scripts\\activate
```

5. Install packages:

```bash
pip install -r requirements.txt
```

6. Start the website:

```bash
python app.py
```

7. Open `http://127.0.0.1:5000` in your browser.
8. Register a new account and sign in.

## Run on macOS/Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Project structure
```text
TradeNexa_AI/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── auth.html
│   ├── dashboard.html
│   ├── classification.html
│   ├── calculator.html
│   ├── markets.html
│   ├── documents.html
│   ├── shipments.html
│   ├── assistant.html
│   ├── analytics.html
│   └── profile.html
└── static/
    ├── style.css
    └── app.js
```

The SQLite database (`tradenexa.db`) is created automatically on first run.
For deployment, set a strong `SECRET_KEY`, disable Flask debug mode, use HTTPS, and add CSRF protection and production-grade security controls.
