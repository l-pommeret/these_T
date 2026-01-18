import re
import json
import urllib.request
import urllib.error
import argparse
import os
import sys
import time
import subprocess
import ssl
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# API Configuration
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ZOTERO_API_URL = "https://t0guvf0w17.execute-api.us-east-1.amazonaws.com/Prod/web"
API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Safety settings
LLM_TIMEOUT = 60
FETCH_TIMEOUT = 20
MAX_WORKERS = 5 

# Create unverified context for problematic SSL certificates
ssl_context = ssl._create_unverified_context()
save_lock = threading.Lock()

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.in_script = False
    def handle_starttag(self, tag, attrs):
        if tag in ['script', 'style']: self.in_script = True
    def handle_endtag(self, tag):
        if tag in ['script', 'style']: self.in_script = False
    def handle_data(self, data):
        if not self.in_script and data.strip(): self.text.append(data.strip())
    def get_text(self): return " ".join(self.text)

def clean_url(url):
    url = url.strip()
    if ']' in url: url = url.split(']')[0]
    if ')' in url: url = url.split(')')[0]
    return url.strip()

def fetch_zotero_metadata(url):
    try:
        req = urllib.request.Request(
            ZOTERO_API_URL, 
            data=url.encode('utf-8'),
            headers={"Content-Type": "text/plain", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                meta = {
                    'author': None, 'year': None, 'title': item.get('title'),
                    'journal': item.get('publicationTitle') or item.get('journalAbbreviation'),
                    'publisher': item.get('publisher'), 'source': 'zotero'
                }
                creators = item.get('creators', [])
                authors = []
                for c in creators:
                    last = c.get('lastName', '')
                    first = c.get('firstName', '')
                    if last and first: authors.append(f"{last}, {first}")
                    elif last: authors.append(last)
                if authors: meta['author'] = authors
                date = item.get('date', '')
                year_match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', str(date))
                if year_match: meta['year'] = year_match.group(1)
                return meta
    except Exception: pass
    return None

def fetch_page_text(url):
    clean = clean_url(url)
    try:
        req = urllib.request.Request(clean, headers={'User-Agent': 'Mozilla/5.0','Referer': 'https://www.google.com/'})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=ssl_context) as response:
            if clean.lower().endswith('.pdf') or 'application/pdf' in response.headers.get('Content-Type', '').lower():
                tid = threading.get_ident()
                temp_pdf = f"/tmp/enrich_{tid}.pdf"
                with open(temp_pdf, 'wb') as f: f.write(response.read())
                result = subprocess.run(['pdftotext', '-l', '5', temp_pdf, '-'], capture_output=True, text=True, timeout=30)
                text = result.stdout
                if os.path.exists(temp_pdf): os.remove(temp_pdf)
                return text[:15000] if len(text.strip()) > 50 else None
            else:
                html = response.read().decode('utf-8', errors='ignore')
                parser = TextExtractor()
                parser.feed(html)
                return parser.get_text()[:20000]
    except Exception: return None

def query_llm(text):
    if not API_KEY: return None
    prompt = f"Extract BibTeX metadata (author: [Last, First], year: YYYY, title, journal, publisher) from this text. If missing, use null. Return JSON only.\n\nCONTENT:\n{text}"
    data = {"model": "openai/gpt-oss-120b:free","messages": [{"role": "user", "content": prompt}],"response_format": {"type": "json_object"}}
    req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(data).encode('utf-8'), headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as response:
                res = json.loads(response.read().decode('utf-8'))
                if 'choices' in res:
                    raw = res['choices'][0]['message']['content'].strip()
                    if raw.startswith('```'): raw = raw.split('\n', 1)[1].rsplit('\n', 1)[0]
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        parsed['source'] = 'llm'
                        return parsed
        except Exception: time.sleep(5); continue
    return None

def format_author(a):
    if isinstance(a, str): return a
    if isinstance(a, dict):
        last = a.get('last', a.get('Last', ''))
        first = a.get('first', a.get('First', ''))
        if last and first: return f"{last}, {first}"
        return last or first or str(a)
    return str(a)

def parse_bib_entry(header, body):
    match = re.search(r'^([^,]+),\s*(.*)', body, re.DOTALL)
    if not match: return None
    key = match.group(1).strip()
    fields_str = match.group(2).strip()
    if fields_str.endswith('}'): fields_str = fields_str[:-1].strip()
    
    fields = {}
    # Use careful regex to find field = {value} patterns
    # This regex handles multiline values by non-greedy matching until a }, at end of line (or } at end of file)
    pattern = re.compile(r'^\s*(\w+)\s*=\s*\{(.*?)\}(?:\s*,?\s*)$', re.MULTILINE | re.DOTALL)
    
    # Actually, let's just use a more manual split to be ultra-safe
    raw_lines = fields_str.split('\n')
    current_field = None
    current_value = []
    
    for line in raw_lines:
        line_match = re.search(r'^\s*(\w+)\s*=\s*\{(.*)', line, re.DOTALL)
        if line_match:
            if current_field:
                val = "\n".join(current_value).strip()
                if val.endswith('},'): val = val[:-2]
                elif val.endswith('}'): val = val[:-1]
                fields[current_field.lower()] = val
            current_field = line_match.group(1)
            current_value = [line_match.group(2)]
        else:
            current_value.append(line)
            
    if current_field:
        val = "\n".join(current_value).strip()
        if val.endswith('},'): val = val[:-2]
        elif val.endswith('}'): val = val[:-1]
        fields[current_field.lower()] = val
            
    return {'type': header[1:-1].lower(), 'key': key, 'fields': fields}

def serialize_bib_entry(parsed):
    res = f"@{parsed['type']}{{{parsed['key']},\n"
    for f, v in parsed['fields'].items():
        v_clean = v.strip()
        # Final safety to remove extra braces if they leaked in
        if v_clean.startswith('{') and v_clean.endswith('}'): v_clean = v_clean[1:-1]
        res += f"  {f} = {{{v_clean}}},\n"
    res += "}\n"
    return res

def process_entry(header, body):
    parsed = parse_bib_entry(header, body)
    if not parsed: return header, body, False
    
    url = parsed['fields'].get('url') or ""
    if not url and 'note' in parsed['fields']:
        um = re.search(r'\\url\{(.*?)\}', parsed['fields']['note'])
        if um: url = um.group(1).split('](')[-1].strip(')')
    
    url = url.replace('\\_', '_')
    author_val = str(parsed['fields'].get('author', ''))
    year_val = str(parsed['fields'].get('year', ''))
    is_incomplete = ('Anonymous' in author_val or 'n.d.' in year_val)
    
    if not url or not is_incomplete:
        return header, body, False

    name = threading.current_thread().name
    print(f"[{name}] [HYBRID] {url[:50]}...", flush=True)
    
    meta = fetch_zotero_metadata(url)
    if not meta:
        text = fetch_page_text(url)
        if text: meta = query_llm(text)
    
    if not meta: return header, body, False
    
    has_author = meta.get('author') and 'Anonymous' not in str(meta['author'])
    if has_author:
        authors = meta['author']
        if isinstance(authors, list):
            names = [format_author(a) for a in authors if a]
            if names: parsed['fields']['author'] = " and ".join(names)
        else:
            parsed['fields']['author'] = format_author(authors)
            
    if meta.get('year') and 'n.d.' not in str(meta['year']):
        parsed['fields']['year'] = str(meta['year'])
        
    for f in ['journal', 'publisher']:
        if meta.get(f): parsed['fields'][f] = str(meta[f])
    
    print(f"[{name}] [SUCCESS] ({meta.get('source')}) {parsed['fields'].get('author')} ({parsed['fields'].get('year')})", flush=True)
    
    new_str = serialize_bib_entry(parsed)
    h_new = new_str.split('\n', 1)[0] + '\n'
    b_new = new_str.split('\n', 1)[1]
    return h_new, b_new, True

def main(bib_path):
    with open(bib_path, 'r', encoding='utf-8') as f: content = f.read()
    entry_blocks = re.split(r'(^@\w+\{)', content, flags=re.MULTILINE)
    preamble = entry_blocks[0]
    entries = []
    for i in range(1, len(entry_blocks), 2):
        entries.append({'header': entry_blocks[i], 'body': entry_blocks[i+1]})
    
    print(f"Starting atomic HYBRID enrichment (v13) of {len(entries)} entries...", flush=True)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_entry, e['header'], e['body']): i for i, e in enumerate(entries)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                h, b, updated = future.result()
                if updated:
                    entries[idx] = {'header': h, 'body': b}
                    with save_lock:
                        with open(bib_path, 'w', encoding='utf-8') as f:
                            f.write(preamble)
                            for ent in entries:
                                f.write(ent['header'] + ent['body'])
            except Exception as e:
                print(f"Error {idx}: {e}", flush=True)
                
    print(f"Finished {bib_path}.", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    args = parser.parse_args()
    main(args.input)
