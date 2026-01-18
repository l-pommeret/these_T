import os
import re

def scaffold_structure(plan_path="PLAN.txt", base_dir="sous-parties"):
    with open(plan_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_part = None
    current_chap = None
    
    part_roman_map = {1: "I", 2: "II", 3: "III", 4: "IV"}
    
    # Regex structure
    part_regex = re.compile(r'^Partie ([IVX]+) ?:?')
    chap_regex = re.compile(r'^Chapitre (\d+) ?:?')
    sec_regex = re.compile(r'^(\d+\.\d+)\.?\s+(.*)')

    part_num = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check Part
        m_part = part_regex.match(line)
        if m_part:
            part_num += 1 # Auto increment or use roman? Plan uses Roman.
            # actually plan says "Partie I", "Partie II"
            # We can trust the plan's numbering or our counter.
            # Plan text: "Partie I : ..."
            roman = m_part.group(1)
            current_part = roman
            continue
            
        # Check Chapter
        m_chap = chap_regex.match(line)
        if m_chap:
            current_chap = m_chap.group(1)
            continue
            
        # Check Section (1.1. Title)
        m_sec = sec_regex.match(line)
        if m_sec and current_part and current_chap:
            sec_num_str = m_sec.group(1) # e.g. "1.1"
            title = m_sec.group(2).strip()
            
            # Format: sous-parties/I/1/I-1-1.tex
            # sec_num_str is "1.1", so we have Chap 1, Sec 1.
            # Let's split it? OR assume the file name format I-Chap-Sec
            # Plan says "1.1. ...", "1.2. ..." inside Chapter 1.
            
            # Filename construction: {Part}-{SecNumReplaced}.tex ?
            # User example: I-1-1.tex for 1.1 inside Part I.
            # But "1.1" usually means Chapter 1, Section 1. 
            # If line is "1.1. Le traumatisme...", and it is inside Chapter 1.
            # So filename: {Part}-{Chapter}-{SectionIndex}.tex
            
            # Extract section index from "1.1" -> 1.
            # But wait, logic: "1.1" -> Chapter 1, Section 1.
            # Does plan strictly follow this?
            # Chapitre 1
            # 1.1 ...
            # Chapitre 2
            # 2.1 ...
            # So the first digit matches chapter.
            
            parts = sec_num_str.split('.')
            chap_chk = parts[0]
            sec_chk = parts[1]
            
            # Verify consistency? Optional.
            
            filename = f"{current_part}-{chap_chk}-{sec_chk}.tex"
            folder_path = os.path.join(base_dir, current_part, chap_chk)
            file_path = os.path.join(folder_path, filename)
            
            # Create directory
            os.makedirs(folder_path, exist_ok=True)
            
            # Create file if not exists or if we want to update (logic: script overwrites if run again? No, currently skips)
            # User wants to fix existing files. Let's make it overwrite or we delete them first?
            # To be safe, let's just write. But the script currently has "if not os.path.exists".
            # I will modify this to OVERWRITE if the file is just a placeholder (checking size or content?).
            # Or simpler: just overwrite for now since they are placeholders.
            
            # Cleaning Title for LaTeX
            clean_title = title
            # Escape special chars
            clean_title = clean_title.replace('%', '\\%').replace('&', '\\&').replace('_', '\\_')
            
            # French Quotes: "word" -> \og word \fg{}
            # Simple heuristic: alternating replacement
            # But regex is better.
            # Replace "text" with \og text \fg{}
            clean_title = re.sub(r'"(.*?)"', r'\\og \1\\fg{}', clean_title)
            # Also handle single quotes or just standard typographic ones if present?
            # User specifically asked for "guillemets anglais" (") to french.
            
            content = f"\\section{{{clean_title}}}\n\n% Content for {clean_title}\n"
            
            # Force overwrite for now to apply fixes
            with open(file_path, 'w', encoding='utf-8') as f_out:
                f_out.write(content)
            print(f"Updated {file_path}")

if __name__ == "__main__":
    scaffold_structure()
