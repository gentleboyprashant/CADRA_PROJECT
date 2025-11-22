CADRA - Context-Aware Document Risk Analyzer (Demo)

How to run:
1) python -m venv venv
2) # activate venv:
   # Windows: venv\Scripts\activate
   # mac/linux: source venv/bin/activate
3) pip install -r requirements.txt
4) (optional) export OPENAI_API_KEY="sk-..."   # or set in Windows env
5) python app.py
6) Open http://127.0.0.1:5000

Notes:
- If OPENAI_API_KEY not set, heuristics-only fallback is used.
- Do not paste real passwords or extremely sensitive personal data into demo.
