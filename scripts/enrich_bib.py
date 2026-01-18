import re
import urllib.request
import argparse
from html.parser import HTMLParser

class MetaTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs_dict = dict(attrs)
            if 'name' in attrs_dict and 'content' in attrs_dict:
                name = attrs_dict['name']
                content = attrs_dict['content']
                if name.startswith('citation_'):
                    # Handle multiple authors by appending to list?
                    if name == 'citation_author':
                        if 'citation_author' in self.metadata:
                            if isinstance(self.metadata['citation_author'], list):
                                self.metadata['citation_author'].append(content)
                            else:
                                self.metadata['citation_author'] = [self.metadata['citation_author'], content]
                        else:
                            self.metadata['citation_author'] = content
                    else:
                        self.metadata[name] = content

def clean_url(url):
    # Remove markdown link artifacts: "url](url)" or "url)"
    if ']' in url:
        url = url.split(']')[0]
    if ')' in url:
        url = url.split(')')[0]
    return url.strip()

def fetch_metadata(url):
    url = clean_url(url)
    print(f"Fetching metadata for {url}...")
    try:
        # User-Agent to avoid being blocked
        req = urllib.request.Request(
            url, 
            data=None, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Referer': 'https://www.google.com/'
            }
        )
        context = None
        try:
            import ssl
            context = ssl._create_unverified_context()
        except AttributeError:
            pass

        with urllib.request.urlopen(req, timeout=10, context=context) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        parser = MetaTagParser()
        parser.feed(html)
        return parser.metadata
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return {}

def parse_bib_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Simple regex to split entries
    # @type{key, ... }
    # We want to capture the whole entry to replace fields
    # Make sure we handle nested braces if possible, but standard BibTeX usually simple.
    # We'll use a regex that matches @type{key, content}
    
    entries = []
    # logic: find @...{ ... } 
    # This is hard with regex for nested braces.
    # Let's iterate line by line or use a simple state machine.
    
    current_entry = []
    in_entry = False
    
    lines = content.split('\n')
    for line in lines:
        if line.strip().startswith('@'):
            if in_entry:
                entries.append("\n".join(current_entry))
            current_entry = [line]
            in_entry = True
        elif line.strip() == '}' or line.strip() == '},': # closing
             # Risky if } is in value. But standard generated format puts } on new line.
             current_entry.append(line)
             if line.strip().startswith('}'): # Assume end of entry
                 entries.append("\n".join(current_entry))
                 current_entry = []
                 in_entry = False
        else:
            if in_entry:
                current_entry.append(line)
    
    if current_entry and in_entry:
        entries.append("\n".join(current_entry))
        
    return entries

def process_bib(input_path, output_path):
    entries = parse_bib_file(input_path)
    new_entries = []
    
    for entry in entries:
        # Extract URL
        url_match = re.search(r'\\url\{(.*?)\}', entry)
        url = url_match.group(1) if url_match else None
        
        # Also check 'url = {...}' field
        if not url:
            url_match = re.search(r'url\s*=\s*\{(.*?)\}', entry)
            url = url_match.group(1) if url_match else None

        if url and ('openedition' in url or 'cairn' in url or 'persee' in url or 'erudit' in url):
            meta = fetch_metadata(url)
            if meta:
                # Update Entry
                # Determine type: Article or Book?
                # citation_journal_title present -> Article
                # citation_isbn present -> Book?
                
                type_ = "misc"
                if 'citation_journal_title' in meta:
                    type_ = "article"
                elif 'citation_isbn' in meta:
                    type_ = "book"
                
                # Rebuild entry
                # Extract Key
                key_match = re.search(r'@\w+\{(.*?),', entry)
                key = key_match.group(1) if key_match else "unknown"
                
                new_entry = f"@{type_}{{{key},\n"
                
                # Title
                if 'citation_title' in meta:
                    new_entry += f"  title = {{{meta['citation_title']}}},\n"
                
                # Author
                if 'citation_author' in meta:
                    authors = meta['citation_author']
                    if isinstance(authors, list):
                        new_entry += f"  author = {{{' and '.join(authors)}}},\n"
                    else:
                        new_entry += f"  author = {{{authors}}},\n"
                
                # Journal / Publisher
                if 'citation_journal_title' in meta:
                    new_entry += f"  journal = {{{meta['citation_journal_title']}}},\n"
                if 'citation_publisher' in meta:
                    new_entry += f"  publisher = {{{meta['citation_publisher']}}},\n"
                    
                # Date
                if 'citation_publication_date' in meta:
                    # YYYY/MM/DD or YYYY
                    date = meta['citation_publication_date']
                    year = date.split('/')[0]
                    new_entry += f"  year = {{{year}}},\n"
                
                # Volume/Issue
                if 'citation_volume' in meta:
                    new_entry += f"  volume = {{{meta['citation_volume']}}},\n"
                if 'citation_issue' in meta:
                    new_entry += f"  number = {{{meta['citation_issue']}}},\n"
                    
                # Pages
                if 'citation_firstpage' in meta:
                    end = meta.get('citation_lastpage', '')
                    if end:
                         new_entry += f"  pages = {{{meta['citation_firstpage']}--{end}}},\n"
                    else:
                         new_entry += f"  pages = {{{meta['citation_firstpage']}}},\n"
                
                # URL
                new_entry += f"  url = {{{url}}},\n"
                
                # Keep note if original had one? (e.g. accessed date)
                # The original had "Consulté le Date, \url{...}"
                # We just want to extract "Consulté le Date"
                # Regex: Consulté le (.*?), \\url
                access_match = re.search(r'(Consulté le .*?),? \\url', entry)
                if access_match:
                    note_content = access_match.group(1).strip()
                    new_entry += f"  note = {{{note_content}}},\n"
                elif 'note =' in entry:
                     # Fallback: some other note?
                     # Try to capture simple content between braces if possible, or skip
                     pass
                
                new_entry += "}\n"
                new_entries.append(new_entry)
            else:
                new_entries.append(entry)
        else:
            new_entries.append(entry)
            
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines([e + "\n" for e in new_entries])
    print(f"Enriched bibliography written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help="Input bib file")
    parser.add_argument('output', help="Output bib file")
    args = parser.parse_args()
    
    process_bib(args.input, args.output)
