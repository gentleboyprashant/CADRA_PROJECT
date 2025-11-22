# create_cadra_files.py
# Run this in an empty folder to create the CADRA project files automatically.

import os, textwrap

files = {
"requirements.txt": textwrap.dedent("""\
Flask==2.2.5
openai==1.3.0
pandas==2.2.2
numpy==1.25.2
python-dotenv==1.0.0
"""),
"app.py": textwrap.dedent("""\
from flask import Flask, render_template, request, redirect, url_for
from detector import analyze
import os

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/analyze", methods=["POST"])
def run_analyze():
    text = request.form.get("doc_text", "").strip()
    if not text:
        return redirect(url_for("index"))
    report = analyze(text)
    return render_template("result.html", text=text, report=report)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
"""),
"detector.py": textwrap.dedent("""\
import re, os, json
from collections import Counter

try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_AVAILABLE and OPENAI_KEY:
    openai.api_key = OPENAI_KEY

TOXIC_WORDS = set([
    "stupid","idiot","dumb","kill","hate","worthless","trash","moron","screw you","shut up"
])

SUSPICIOUS_PHRASES = [
    "send money", "transfer", "click here", "login", "password", "bank", "account number",
    "upi", "paytm", "paypal", "send rs", "pay now"
]

COMMON_TEMPLATES = [
    "this report discusses", "in conclusion", "the purpose of this document is",
    "the results show that", "for more information", "please contact us"
]

RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RE_PHONE = re.compile(r"\b(?:\+?91[\-\s]?)?[6-9]\d{9}\b|\b\d{3}[\-\s]\d{3}[\-\s]\d{4}\b")
RE_AADHAAR = re.compile(r"\b\d{4}\s*\d{4}\s*\d{4}\b")
RE_NUMERIC_LONG = re.compile(r"\b\d{9,}\b")
RE_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RE_URL = re.compile(r"https?://\S+|\bwww\.\S+")

def find_sensitive_items(text: str):
    found = {
        "emails": RE_EMAIL.findall(text),
        "phones": RE_PHONE.findall(text),
        "urls": RE_URL.findall(text),
        "aadhar_like": RE_AADHAAR.findall(text),
        "long_numbers": RE_NUMERIC_LONG.findall(text),
        "ips": RE_IP.findall(text),
    }
    for k in list(found.keys()):
        found[k] = list(dict.fromkeys(found[k]))
    return found

def simple_tone_and_toxicity(text: str):
    text_low = text.lower()
    toxic_hits = [w for w in TOXIC_WORDS if w in text_low]
    suspicious_hits = [p for p in SUSPICIOUS_PHRASES if p in text_low]
    exclam = text.count("!")
    caps_words = sum(1 for w in re.findall(r"\b[A-Z]{2,}\b", text))
    questions = text.count("?")
    tone = 50
    tone -= len(toxic_hits) * 20
    tone -= len(suspicious_hits) * 8
    tone -= min(caps_words,5) * 3
    tone -= min(exclam,5) * 2
    tone += min(questions,3) * 1
    tone = max(0, min(100, tone))
    return {
        "toxic_hits": toxic_hits,
        "suspicious_hits": suspicious_hits,
        "exclamations": exclam,
        "caps_words": caps_words,
        "questions": questions,
        "tone_score": tone
    }

def structure_and_clarity(text: str):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s for s in sentences if s.strip()]
    words = re.findall(r"\w+", text)
    avg_sentence_len = (sum(len(s.split()) for s in sentences) / len(sentences)) if sentences else 0
    avg_word_len = (sum(len(w) for w in words) / len(words)) if words else 0
    long_sentences = [s for s in sentences if len(s.split()) > 30]
    return {
        "num_sentences": len(sentences),
        "num_words": len(words),
        "avg_sentence_len": round(avg_sentence_len,2),
        "avg_word_len": round(avg_word_len,2),
        "long_sentences_count": len(long_sentences)
    }

def plagiarism_hint(text: str):
    low = text.lower()
    hits = [t for t in COMMON_TEMPLATES if t in low]
    phrases = re.findall(r"\b\w{4,}\b", low)
    c = Counter(phrases)
    repeated_phrases = [w for w,n in c.items() if n>5][:10]
    return {"template_hits": hits, "repeated_terms": repeated_phrases}

def llm_analyze_openai(text: str):
    if not OPENAI_AVAILABLE or not OPENAI_KEY:
        return None
    system_prompt = (
        "You are Document Safety Assistant. Analyze the provided document and return a JSON "
        "with fields: 'summary' (1-2 sentence), 'issues' (list of short strings), "
        "'rewrite_suggestions' (list of up to 3 suggested rewrites of risky sentences), "
        "'advice' (list of 3 concrete actions). Only return valid JSON."
    )
    user_prompt = f"Document:\n'''{text}'''\nProvide result as JSON."
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini" if hasattr(openai, "ChatCompletion") else "gpt-4o",
            messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_prompt}],
            temperature=0.2,
            max_tokens=450
        )
        txt = resp['choices'][0]['message']['content']
        j = None
        try:
            jtxt = txt.strip()
            start = jtxt.find('{')
            end = jtxt.rfind('}')
            if start!=-1 and end!=-1:
                j = json.loads(jtxt[start:end+1])
        except Exception:
            j = {"raw": txt}
        return j
    except Exception as e:
        return {"error": f"LLM call failed: {str(e)}"}

def llm_analyze_fallback(text: str):
    sensitive = find_sensitive_items(text)
    tone = simple_tone_and_toxicity(text)
    struct = structure_and_clarity(text)
    pl = plagiarism_hint(text)
    issues = []
    if sensitive['emails'] or sensitive['phones'] or sensitive['aadhar_like'] or sensitive['long_numbers']:
        issues.append("Contains potential personally identifiable information (PII).")
    if tone['toxic_hits']:
        issues.append("Contains toxic or insulting language.")
    if tone['suspicious_hits']:
        issues.append("Contains suspicious phrases (payment/login/request).")
    if pl['template_hits']:
        issues.append("Contains common template phrases; check originality.")
    if struct['long_sentences_count']>0:
        issues.append("Contains very long sentences; consider breaking for clarity.")
    summary = "The document has " + (", ".join(issues) if issues else "no immediate obvious red flags.")
    rewrites = []
    if sensitive['phones']:
        rewrites.append("Remove phone numbers or redact them like +91-XXXXXXXXXX.")
    if tone['toxic_hits']:
        rewrites.append("Replace insulting phrases with neutral language.")
    if not rewrites:
        rewrites.append("Document appears generally fine; improve clarity if needed.")
    advice = [
        "Redact any PII before publishing.",
        "Use neutral tone; avoid accusatory language.",
        "Break long sentences; add citations where needed."
    ]
    return {"summary": summary, "issues": issues, "rewrite_suggestions": rewrites, "advice": advice}

def analyze(text: str):
    s = find_sensitive_items(text)
    tone = simple_tone_and_toxicity(text)
    struct = structure_and_clarity(text)
    pl = plagiarism_hint(text)
    score = 0
    if s['emails']: score += 20
    if s['phones']: score += 20
    if s['aadhar_like'] or s['long_numbers']: score += 25
    score += min(20, len(tone['suspicious_hits'])*6)
    score += min(20, len(tone['toxic_hits'])*12)
    score += max(0, (50 - tone['tone_score'])//2)
    score += min(10, struct['long_sentences_count']*3)
    score += min(10, len(pl['template_hits'])*5)
    score = int(max(0, min(100, score)))
    llm_result = None
    if OPENAI_AVAILABLE and OPENAI_KEY:
        llm_out = llm_analyze_openai(text)
        if llm_out:
            llm_result = llm_out
    else:
        llm_result = llm_analyze_fallback(text)
    evidence = []
    if s['emails']: evidence.append(f"Emails found: {len(s['emails'])}")
    if s['phones']: evidence.append(f"Phone numbers found: {len(s['phones'])}")
    if s['urls']: evidence.append(f"URLs found: {len(s['urls'])}")
    if tone['toxic_hits']: evidence.append(f"Toxic words: {', '.join(tone['toxic_hits'])}")
    if tone['suspicious_hits']: evidence.append(f"Suspicious phrases: {', '.join(tone['suspicious_hits'])}")
    if pl['template_hits']: evidence.append(f"Common templates matched: {', '.join(pl['template_hits'])}")
    report = {
        "score": score,
        "risk_level": ("High" if score>=61 else "Medium" if score>=31 else "Low"),
        "evidence": evidence,
        "sensitive": s,
        "tone": tone,
        "structure": struct,
        "plagiarism_hint": pl,
        "llm": llm_result
    }
    return report
"""),
"templates/index.html": textwrap.dedent("""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CADRA - Document Risk Analyzer (Demo)</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:20px auto;padding:10px}
    textarea{width:100%;height:300px;padding:8px;font-size:14px}
    button{padding:8px 12px;margin-top:8px}
    .note{color:#555;font-size:0.95em}
  </style>
</head>
<body>
  <h2>CADRA — Context-Aware Document Risk Analyzer (Demo)</h2>
  <p class="note">Paste your document text here (no passwords). This demo runs local heuristics; set OPENAI_API_KEY in environment for LLM-enhanced analysis.</p>
  <form method="post" action="/analyze">
    <textarea name="doc_text" placeholder="Paste document, email, resume, or message..."></textarea>
    <br>
    <button type="submit">Analyze Document</button>
  </form>
  <hr>
  <p>Example: paste "Contact: prashant@example.com. Please send money to account 123456789. You are stupid!"</p>
</body>
</html>
"""),
"templates/result.html": textwrap.dedent("""\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CADRA — Analysis Result</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:18px auto;padding:10px}
    .box{border:1px solid #ddd;padding:12px;border-radius:6px;margin-bottom:12px}
    .high{color:#b30000} .med{color:#b36b00} .low{color:#1a7300}
    pre{white-space:pre-wrap;word-wrap:break-word}
  </style>
</head>
<body>
  <a href="/">← Back</a>
  <h2>Analysis Result</h2>
  <div class="box">
    <p>Risk Score: <strong>{{ report.score }}</strong> — Risk Level:
       <span class="{{ 'high' if report.risk_level=='High' else 'med' if report.risk_level=='Medium' else 'low' }}">{{ report.risk_level }}</span></p>
    <p><strong>Evidence:</strong></p>
    <ul>
      {% for e in report.evidence %}
        <li>{{ e }}</li>
      {% endfor %}
      {% if report.evidence|length == 0 %}
        <li>No immediate deterministic issues found.</li>
      {% endif %}
    </ul>
  </div>

  <div class="box">
    <h3>Sensitive Items Detected</h3>
    <ul>
      <li>Emails: {{ report.sensitive.emails|length }}</li>
      <li>Phones: {{ report.sensitive.phones|length }}</li>
      <li>URLs: {{ report.sensitive.urls|length }}</li>
      <li>Aadhar-like: {{ report.sensitive.aadhar_like|length }}</li>
    </ul>
  </div>

  <div class="box">
    <h3>Tone & Toxicity (heuristic)</h3>
    <p>Tone score (0 worst — 100 neutral/good): <strong>{{ report.tone.tone_score }}</strong></p>
    <p>Toxic words: {{ report.tone.toxic_hits }}</p>
    <p>Suspicious phrases: {{ report.tone.suspicious_hits }}</p>
  </div>

  <div class="box">
    <h3>Structure & Clarity</h3>
    <ul>
      <li>Sentences: {{ report.structure.num_sentences }}</li>
      <li>Words: {{ report.structure.num_words }}</li>
      <li>Avg sentence length (words): {{ report.structure.avg_sentence_len }}</li>
      <li>Long sentences flagged: {{ report.structure.long_sentences_count }}</li>
    </ul>
  </div>

  <div class="box">
    <h3>LLM Analysis / Suggestions</h3>
    {% if report.llm %}
      {% if report.llm.raw %}
        <pre>{{ report.llm.raw }}</pre>
      {% else %}
        <p><strong>Summary:</strong> {{ report.llm.get('summary','-') }}</p>
        <p><strong>Issues:</strong></p>
        <ul>{% for it in report.llm.get('issues',[]) %}<li>{{ it }}</li>{% endfor %}</ul>
        <p><strong>Rewrite Suggestions:</strong></p>
        <ul>{% for it in report.llm.get('rewrite_suggestions',[]) %}<li>{{ it }}</li>{% endfor %}</ul>
        <p><strong>Advice:</strong></p>
        <ul>{% for it in report.llm.get('advice',[]) %}<li>{{ it }}</li>{% endfor %}</ul>
      {% endif %}
    {% else %}
      <p>No LLM analysis available (no API). Fallback heuristics applied.</p>
    {% endif %}
  </div>

  <div class="box">
    <h3>Original Document</h3>
    <pre>{{ text }}</pre>
  </div>
</body>
</html>
"""),
"README.md": textwrap.dedent("""\
CADRA - Context-Aware Document Risk Analyzer (Demo)

How to run:
1) python -m venv venv
2) # activate venv:
   # Windows: venv\\Scripts\\activate
   # mac/linux: source venv/bin/activate
3) pip install -r requirements.txt
4) (optional) export OPENAI_API_KEY=\"sk-...\"   # or set in Windows env
5) python app.py
6) Open http://127.0.0.1:5000

Notes:
- If OPENAI_API_KEY not set, heuristics-only fallback is used.
- Do not paste real passwords or extremely sensitive personal data into demo.
""")
}

# create folders
os.makedirs("templates", exist_ok=True)

for path,content in files.items():
    # ensure directories
    fullpath = path
    d = os.path.dirname(fullpath)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(fullpath, "w", encoding="utf-8") as f:
        f.write(content)
print("Files created. Run: python -m venv venv ; activate venv ; pip install -r requirements.txt ; python app.py")
