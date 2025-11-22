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
RE_PHONE = re.compile(r"(?:\+?91[\-\s]?)?[6-9]\d{9}|\d{3}[\-\s]\d{3}[\-\s]\d{4}")
RE_AADHAAR = re.compile(r"\d{4}\s*\d{4}\s*\d{4}")
RE_NUMERIC_LONG = re.compile(r"\d{9,}")
RE_IP = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
RE_URL = re.compile(r"https?://\S+|www\.\S+")

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
    caps_words = sum(1 for w in re.findall(r"[A-Z]{2,}", text))
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
    phrases = re.findall(r"\w{4,}", low)
    c = Counter(phrases)
    repeated_phrases = [w for w,n in c.items() if n>5][:10]
    return {"template_hits": hits, "repeated_terms": repeated_phrases}

def llm_analyze_openai(text: str):
    """
    Safe OpenAI LLM call with escaped text & fallback.
    """
    if not OPENAI_AVAILABLE or not OPENAI_KEY:
        return None

    # Escape text to avoid breaking prompt
    safe_text = (
        text.replace('\\', '\\\\')
            .replace('{', '{{')
            .replace('}', '}}')
    )

    system_prompt = (
        "You are Document Safety Assistant. Analyze the provided document and return a JSON "
        "with fields: 'summary' (1-2 sentence), 'issues' (list of short strings), "
        "'rewrite_suggestions' (list of up to 3 suggested rewrites), "
        "'advice' (list of concrete actions). Only return valid JSON."
    )

    user_prompt = "Document:\n'''{}'''\nProvide result as JSON.".format(safe_text)

    try:
        if hasattr(openai, "ChatCompletion"):
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=450
            )
            txt = resp['choices'][0]['message']['content']
        else:
            resp = openai.Completion.create(
                model="gpt-4o",
                prompt=system_prompt + "\n\n" + user_prompt,
                temperature=0.2,
                max_tokens=450
            )
            txt = resp['choices'][0]['text']

        # Parse JSON from response
        try:
            jtxt = txt.strip()
            start = jtxt.find('{')
            end = jtxt.rfind('}')
            if start != -1 and end != -1:
                return json.loads(jtxt[start:end + 1])
            return {"raw": txt}
        except:
            return {"raw": txt}

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
