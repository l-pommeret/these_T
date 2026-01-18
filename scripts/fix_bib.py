import re
import argparse
import sys

def fix_bib(bib_file):
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {bib_file}: {e}")
        return

    # Pattern to find the start of an entry
    entry_starts = [m.start() for m in re.finditer(r'^@\w+\{', content, re.MULTILINE)]
    entry_starts.append(len(content))

    new_chunks = []
    # If there is content before the first entry, keep it
    if entry_starts[0] > 0:
        new_chunks.append(content[0:entry_starts[0]])

    for i in range(len(entry_starts)-1):
        chunk = content[entry_starts[i]:entry_starts[i+1]]
        
        # Check fields in this chunk
        if not re.search(r'^\s*author\s*=', chunk, re.IGNORECASE | re.MULTILINE):
            # Inject after key line (first line ending with comma)
            chunk = re.sub(r'(\,\s*\n)', r'\1  author = {Anonymous},\n', chunk, count=1)
            
        if not re.search(r'^\s*year\s*=', chunk, re.IGNORECASE | re.MULTILINE):
            # Inject after key line or below author line
            chunk = re.sub(r'(\,\s*\n)', r'\1  year = {n.d.},\n', chunk, count=1)

        new_chunks.append(chunk)

    with open(bib_file, 'w', encoding='utf-8') as f:
        f.write("".join(new_chunks))
    print(f"Fixed {bib_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help="Input bib file")
    args = parser.parse_args()
    fix_bib(args.input)
