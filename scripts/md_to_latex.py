
import re
import os
import argparse
import textwrap

def parse_markdown(md_content):
    """
    Parses the markdown content to separate the body from the bibliography
    and converts the body to LaTeX.
    """
    lines = md_content.split('\n')
    body_lines = []
    bib_lines = []
    in_bib = False
    
    # 1. Separate Body and Bibliography
    # We look for "Works cited" or "Bibliographie" to start the bib section
    for line in lines:
        if re.search(r'^\s*#{2,}\s*(\*+)?(Works cited|Bibliographie)(\*+)?', line, re.IGNORECASE):
            in_bib = True
            continue # specific header not needed in tex body if we use bibtex
        
        if in_bib:
            if line.strip(): # ignore empty lines in bib section
                bib_lines.append(line.strip())
        else:
            body_lines.append(line)

    return body_lines, bib_lines

def generate_bibtex(bib_lines, prefix=""):
    """
    Parses the extracted bibliography lines and creates BibTeX entries.
    Expected format: "1. [Title] - [Source], accessed [Date], [Link]"
    Attempts to extract Author (if present in Title as "par Author"), Source, Date, and URL.
    """
    bib_entries = []
    entry_map = {} # Map ID (e.g., "1") to BibTeX key (e.g., "ref1")

    # Regex to capture: ID, Title+Author, Source, Date, URL
    regex_smart = re.compile(r'^(\d+)\.\s+(.*?)(?:\s+\\?-\s+)(.*?), accessed (.*?), (?:\[)?(https?://.*?)(?:\]\(.*?\)|$)?$')

    for line in bib_lines:
        line = line.strip()
        if not line:
            continue
            
        ref_id = None
        title_raw = ""
        source = ""
        access_date = ""
        url = ""
        note = ""
        author = ""
        
        match_smart = regex_smart.match(line)
        if match_smart:
            ref_id = match_smart.group(1)
            title_raw = match_smart.group(2).strip()
            source = match_smart.group(3).strip()
            access_date = match_smart.group(4).strip()
            url = match_smart.group(5).strip()
            
            # Frenchify access date if it is "January 17, 2026" -> "17 janvier 2026" ?
            note = f"Consulté le {access_date}"
            
            # Author Extraction
            m_author = re.search(r', par (.*)$', title_raw, re.IGNORECASE)
            if m_author:
                author = m_author.group(1).strip()
                title_raw = title_raw[:m_author.start()].strip()
            elif ' / ' in title_raw:
                parts = title_raw.rsplit(' / ', 1)
                title_raw = parts[0].strip()
                author = parts[1].strip()
            
            howpublished = source
            
        else:
            # Fallback to simple parser
            match = re.match(r'^(\d+)\.\s+(.*)', line)
            if match:
                ref_id = match.group(1)
                content = match.group(2)
                url_match = re.search(r'(https?://\S+)', content)
                if url_match:
                    url = url_match.group(1)
                    content = content.replace(url, "").strip().rstrip(",").rstrip()
                
                title_raw = content
                note = " Référence extraite automatiquement" # fallback note

        if ref_id:
            if prefix:
                bib_key = f"{prefix}ref{ref_id}"
            else:
                bib_key = f"ref{ref_id}"
                
            entry_map[ref_id] = bib_key
            
            # Clean fields for LaTeX
            def clean_tex(s):
                if not s: return ""
                # Unescape md
                s = s.replace('\\_', '_').replace('\\%', '%').replace('\\&', '&')
                # Escape tex
                s = s.replace('_', '\\_').replace('%', '\\%').replace('&', '\\&')
                return s
            
            title = clean_tex(title_raw)
            author = clean_tex(author)
            howpublished = clean_tex(source)
            note = clean_tex(note)
            
            # Construct BibTeX entry
            bib_entry = f"@misc{{{bib_key},\n"
            bib_entry += f"  title = {{{title}}},\n"
            if author:
                bib_entry += f"  author = {{{author}}},\n"
            if howpublished:
                bib_entry += f"  howpublished = {{{howpublished}}},\n"
            
            # Combine note and url for safety in 'plain' style
            full_note = note
            if url:
                 full_note += f", \\url{{{url}}}"
            
            bib_entry += f"  note = {{{full_note}}},\n"
            bib_entry += "}\n"
            
            bib_entries.append(bib_entry)
            
    return bib_entries, entry_map

def frenchify_title(title):
    """
    Converts a title to sentence case (uppercase first letter, rest lowercase),
    but respecting Roman numerals.
    """
    if not title:
        return ""
    
    lowered = title.lower()
    # Capitalize first char
    if len(lowered) > 0:
        lowered = lowered[0].upper() + lowered[1:]
        
    # Fix Roman numerals at start: "i. ..." -> "I. ..."
    match = re.match(r'^([ivxlcdm]+)(\.?)', lowered)
    if match:
        roman = match.group(1).upper()
        punct = match.group(2)
        lowered = roman + punct + lowered[len(roman)+len(punct):]
        
        # Also capitalize the letter immediately following the roman numeral + space/dot
        remaining = lowered[len(roman)+len(punct):]
        match_text = re.search(r'[a-zA-Zà-üÀ-Ü]', remaining)
        if match_text:
            idx = match_text.start() + len(roman) + len(punct)
            lowered = lowered[:idx] + lowered[idx].upper() + lowered[idx+1:]
            
    return lowered

def format_text_latex(text, entry_map):
    # French Quotes: "word" -> \og word \fg{}
    text = re.sub(r'"(.*?)"', r'\\og \1\\fg{}', text)

    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
    # Italic
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)
    
    # Citations
    def replace_match(m):
        punct = m.group(1)
        number = m.group(2)
        if number in entry_map:
            return f"{punct}\\cite{{{entry_map[number]}}}"
        return m.group(0)

    text = re.sub(r'([.?!»])\s*(\d+)(?=\s|$)', replace_match, text)

    # Unescape
    text = text.replace('\\.', '.')
    text = text.replace('\\)', ')').replace('\\(', '(')
    
    # Normalize and Re-escape special chars
    text = text.replace('\\_', '_').replace('_', '\\_')
    text = text.replace('\\%', '%').replace('%', '\\%')
    text = re.sub(r'(?<!\\)&', r'\\&', text)
    
    return text

def process_table(table_lines, entry_map):
    if not table_lines:
        return []
    
    # Parse header
    header_line = table_lines[0]
    headers = [cell.strip() for cell in header_line.strip('|').split('|')]
    
    # Check for separator/alignment row
    body_start_idx = 1
    if len(table_lines) > 1 and set(table_lines[1].strip()) <= set('| -:'):
        body_start_idx = 2

    # Determine columns (naive: left align everything or 'l' * count)
    col_count = len(headers)
    col_string = " | ".join(["l"] * col_count)
    col_spec = f"| {col_string} |"
    
    latex_out = []
    latex_out.append(r"\begin{table}[h!]")
    latex_out.append(r"\centering")
    latex_out.append(f"\\begin{{tabular}}{{{col_spec}}}")
    latex_out.append(r"\hline")
    
    # Header row
    formatted_headers = []
    for h in headers:
        formatted_headers.append(f"\\textbf{{{format_text_latex(h, entry_map)}}}")
    latex_out.append(" & ".join(formatted_headers) + r" \\ \hline")
    
    # Body rows
    for row_line in table_lines[body_start_idx:]:
        full_cells = row_line.strip('|').split('|')
        cells = [c.strip() for c in full_cells]
        if len(cells) > col_count:
            cells = cells[:col_count]
        elif len(cells) < col_count:
            cells += [""] * (col_count - len(cells))
            
        formatted_cells = [format_text_latex(c, entry_map) for c in cells]
        latex_out.append(" & ".join(formatted_cells) + r" \\ \hline")
        
    latex_out.append(r"\end{tabular}")
    latex_out.append(r"\end{table}")
    return latex_out

def convert_to_latex(body_lines, entry_map, base_level=1):
    """
    Converts markdown body lines to LaTeX, replacing citations and headers.
    """
    latex_lines = []
    
    # Map integers to LaTeX commands
    header_regex = re.compile(r'^(#+)\s+(.*)')
    bold_header_regex = re.compile(r'^(\*\*|__)(.*?)\1$')
    separator_regex = re.compile(r'^(?:#+\s*)?---+$')
    
    level_map = {
        -1: "part",
        0: "chapter",
        1: "section",
        2: "subsection",
        3: "subsubsection",
        4: "paragraph",
        5: "subparagraph"
    }

    in_itemize = False
    table_buffer = []

    for line in body_lines:
        line = line.strip()
        
        # 0. Table Handling: Buffer lines if they start with '|'
        if line.startswith('|'):
            table_buffer.append(line)
            continue
        else:
            if table_buffer:
                # Flush table buffer
                latex_lines.extend(process_table(table_buffer, entry_map))
                table_buffer = []
        
        if not line:
            if in_itemize:
                latex_lines.append(r"\end{itemize}")
                in_itemize = False
            latex_lines.append("")
            continue

        # 1. Separator Handling: Skip completely
        if separator_regex.match(line):
            continue

        # 2. List Handling
        list_match = re.match(r'^(\*|-)\s+(.*)', line)
        if list_match:
            if not in_itemize:
                latex_lines.append(r"\begin{itemize}")
                in_itemize = True
            content = list_match.group(2)
            
            # Apply formatting to content using centralized function
            content = format_text_latex(content, entry_map)
            
            latex_lines.append(f"\\item {content}")
            continue
        else:
            if in_itemize:
                latex_lines.append(r"\end{itemize}")
                in_itemize = False

        # 3. Header Detection
        current_level = None
        title = None
        
        m_hash = header_regex.match(line)
        if m_hash:
            current_level = len(m_hash.group(1))
            title = m_hash.group(2)
        else:
            m_bold = bold_header_regex.match(line)
            if m_bold:
                title_content = m_bold.group(2)
                # Heuristic: If starts with Roman Numeral "I.", etc
                if re.match(r'^[IVXLCDM]+\.', title_content, re.IGNORECASE):
                    current_level = 2
                else:
                    current_level = 6 # Text Paragraph otherwise
                title = title_content

        if current_level is not None and title:
            # Strip wrapping bold markers from headers
            bold_wrapper_match = re.match(r'^(\*\*|__)(.*?)\1$', title)
            if bold_wrapper_match:
                title = bold_wrapper_match.group(2)

            # Header Numbering Stripping
            # Remove patterns like "I.", "I.1", "1.1." at the start of the title
            # Regex looks for groups of (Alphanum + dot) occurring at least once.
            # We strictly enforce that it must end with whitespace to avoid damaging words.
            # We also ensure it contains at least one dot to differentiate from years like "1880".
            title = re.sub(r'^([IVXLCDM0-9]+\.)+[IVXLCDM0-9]*\s*', '', title)

            # Frenchify title casing
            title = frenchify_title(title)
            
            # Apply formatting to the title (Bold/Italic)
            title = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', title)
            title = re.sub(r'\*(.*?)\*', r'\\textit{\1}', title)

            # Skip Introduction Headers COMPLETELY
            if "introduction" in title.lower():
                continue

            # Unescape special chars in title for LaTeX
            title = title.replace('&', '\\&').replace('%', '\\%')

            # Determine effective LaTeX level
            effective_level = current_level + (base_level - 1)
            
            if effective_level in level_map and effective_level <= 4: 
                command = level_map[effective_level]
                # Add blank line before and after header for readability
                # Use literal newlines \n not escaped \\n
                latex_lines.append(f"\n\n\\{command}{{{title}}}\n\n")
            else:
                pass
            continue
            
        # 4. Text Formatting (Bold/Italic, Quotes, Citations, Escaping)
        formatted_line = format_text_latex(line, entry_map)
        
        # 5. Wrapping for readability
        wrapped_lines = textwrap.fill(formatted_line, width=100)

        # Double newline for paragraph separation (Aéré)
        latex_lines.append(wrapped_lines + "\n\n")

    # Flush table buffer if exists at EOF
    if table_buffer:
        latex_lines.extend(process_table(table_buffer, entry_map))
        
    if in_itemize:
        latex_lines.append(r"\end{itemize}" + "\n\n")
    return latex_lines


def main():
    parser = argparse.ArgumentParser(description="Convert Thesis Markdown to LaTeX")
    parser.add_argument('input_md', help="Input Markdown file")
    parser.add_argument('--base-level', type=int, default=1, 
                        help="Base LaTeX level for the top-level header (#). -1=part, 0=chapter, 1=section, etc.")
    parser.add_argument('--bib-prefix', type=str, default="", 
                        help="Prefix for BibTeX keys to ensure uniqueness across chapters.")
    args = parser.parse_args()

    input_path = args.input_md
    base_name = os.path.splitext(input_path)[0]
    tex_output = base_name + ".tex"
    bib_output = base_name + ".bib"

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    body_lines, bib_lines = parse_markdown(content)
    bib_entries, entry_map = generate_bibtex(bib_lines, prefix=args.bib_prefix)
    latex_lines = convert_to_latex(body_lines, entry_map, base_level=args.base_level)

    # Write BibTeX
    with open(bib_output, 'w', encoding='utf-8') as f:
        f.writelines(bib_entries)
    
    # Write LaTeX
    with open(tex_output, 'w', encoding='utf-8') as f:
        f.writelines(latex_lines)

    print(f"Generated {tex_output} and {bib_output}")

if __name__ == "__main__":
    main()
