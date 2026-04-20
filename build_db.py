import sqlite3
import json
import glob
import re
import os
import markdown
import bleach
import html

DB_FILE = 'kice_database.sqlite'
CONCEPTS_FILE = 'concepts.json'
SOLUTIONS_DIR = 'Sol/*/*.md'

def setup_database():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables based on the plan
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS concepts (
            id TEXT PRIMARY KEY,
            curriculum_unit TEXT,
            standard_name TEXT,
            keywords TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS problems (
            problem_id TEXT PRIMARY KEY,
            year INTEGER,
            exam_type TEXT,
            subject_type TEXT,
            question_no INTEGER,
            answer TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS triggers (
            trigger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trigger_text TEXT UNIQUE,
            normalized_text TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS steps (
            step_id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id TEXT,
            step_number INTEGER,
            step_title TEXT,
            explanation_text TEXT,
            explanation_html TEXT,
            action_concept_id TEXT,
            action_text TEXT,
            result_text TEXT,
            FOREIGN KEY(problem_id) REFERENCES problems(problem_id),
            FOREIGN KEY(action_concept_id) REFERENCES concepts(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS step_triggers (
            step_id INTEGER,
            trigger_id INTEGER,
            FOREIGN KEY(step_id) REFERENCES steps(step_id),
            FOREIGN KEY(trigger_id) REFERENCES triggers(trigger_id),
            PRIMARY KEY(step_id, trigger_id)
        )
    ''')
    
    conn.commit()
    return conn

def load_concepts(conn):
    cursor = conn.cursor()
    try:
        with open(CONCEPTS_FILE, 'r', encoding='utf-8') as f:
            concepts = json.load(f)
            for c in concepts:
                cursor.execute('''
                    INSERT INTO concepts (id, curriculum_unit, standard_name, keywords)
                    VALUES (?, ?, ?, ?)
                ''', (c.get('id'), c.get('curriculum_unit'), c.get('standard_name'), json.dumps(c.get('keywords', []) if isinstance(c.get('keywords'), list) else [], ensure_ascii=False)))
    except FileNotFoundError:
        print(f"Warning: {CONCEPTS_FILE} not found.")
    conn.commit()

def parse_metadata_from_filename(filename):
    import unicodedata
    basename = os.path.basename(filename).replace('.md', '')
    basename = unicodedata.normalize('NFC', basename)  # Normalize macOS NFD filenames
    # format examples: 2026.6모_01, 2026.9모_09, 2026수능_01
    #                  2016수능A_11, 2017.6모나_19
    match = re.search(r'(\d{4})\.?([가-힣A-Za-z\d]+)_(확|기|미|A|B)?(\d+)', basename)
    if match:
        year = int(match.group(1))
        exam_type = match.group(2)  # "6모", "수능A", "6모나"
        prefix = match.group(3)     # "확", "기", "미", "A", "B" or None
        question_no = int(match.group(4))
        prefix_map = {'확': '확통', '기': '기하', '미': '미적분', 'A': '가형', 'B': '나형'}
        subject_type = prefix_map.get(prefix, '공통')
        return basename, year, exam_type, subject_type, question_no
    return basename, None, None, None, None

def is_result_trigger(text):
    """'Step N의 Result' 패턴이 포함된 트리거를 걸러냄. 벡터 임베딩이 이 역할을 대신함."""
    return bool(re.search(r'\[?Step \d+의 Result', text.strip()))

def extract_answer(content, pid):
    """MD 파일 내용에서 정답을 추출합니다. (dashboard.py의 로직 재활용)"""
    try:
        matches = re.finditer(r'정답(?:은|:)?\s*(.+?)(?:입니다|번\s*입니다|번입니다|\.|\n|$)', content)
        found_ans = None
        for m in matches:
            ans_str = m.group(1).strip()
            # 마크다운 스타일, 블록인용구, LaTeX $ 기호 등 제거
            ans_str = re.sub(r'[\*\_>\$]+', '', ans_str).strip()
            
            if not ans_str:
                continue
            
            # 괄호 안의 숫자 추출: (5) -> 5
            paren_match = re.match(r'^\((\d)\)$', ans_str)
            if paren_match:
                ans_str = paren_match.group(1)
            
            is_mcq = False
            if ans_str.endswith('번'):
                ans_str = ans_str[:-1].strip()
                is_mcq = True
            elif paren_match:
                is_mcq = True
            
            # 연도와 문제 번호를 기반으로 객관식 자동 변환 규칙 적용
            try:
                year_val = 2022 # 기본값
                year_extract = re.match(r'^(\d{4})', pid)
                if year_extract:
                    year_val = int(year_extract.group(1))
                
                parts = pid.split('_')
                if len(parts) >= 2:
                    num_part = ''.join(filter(str.isdigit, parts[-1]))
                    if num_part:
                        pnum = int(num_part)
                        if year_val >= 2022:
                            if (1 <= pnum <= 15) or (23 <= pnum <= 28):
                                is_mcq = True
                        else:
                            if (1 <= pnum <= 21):
                                is_mcq = True
            except:
                pass
            
            if is_mcq:
                circled_match = re.search(r'([①②③④⑤])', ans_str)
                if circled_match:
                    ans_str = circled_match.group(1)
                elif ans_str in ['1', '2', '3', '4', '5']:
                    circled_map = {'1':'①', '2':'②', '3':'③', '4':'④', '5':'⑤'}
                    ans_str = circled_map[ans_str]
            
            if ans_str:
                found_ans = ans_str
        
        return found_ans
    except Exception as e:
        print(f"Error extracting answer for {pid}: {e}")
        return None

def get_or_create_trigger(conn, trigger_text):
    cursor = conn.cursor()
    cursor.execute('SELECT trigger_id FROM triggers WHERE trigger_text = ?', (trigger_text,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        cursor.execute('INSERT INTO triggers (trigger_text) VALUES (?)', (trigger_text,))
        return cursor.lastrowid

def parse_solutions(conn):
    cursor = conn.cursor()
    files = glob.glob(SOLUTIONS_DIR)
    
    for filepath in files:
        problem_id, year, exam_type, subject_type, qno = parse_metadata_from_filename(filepath)
        if not year:
            continue
            
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 정답 추출
        answer = extract_answer(content, problem_id)
            
        cursor.execute('''
            INSERT OR REPLACE INTO problems (problem_id, year, exam_type, subject_type, question_no, answer)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (problem_id, year, exam_type, subject_type, qno, answer))
            
        # Parse steps using regex
        # Look for blocks that start with ## [Step N] <title>
        step_matches = list(re.finditer(r'## \[Step (\d+)\]([^\n]*)\n(.*?)(?=(?:## \[Step \d+\])|\Z)', content, re.DOTALL))
        
        for match in step_matches:
            step_num = int(match.group(1))
            step_title = match.group(2).strip()
            block = match.group(3)
            trigger_match = re.search(r'- \*\*Trigger\*\*:\s*(.*?)\n- \*\*Action\*\*', block, re.DOTALL)
            action_match = re.search(r'- \*\*Action\*\*:\s*(?:\[(.*?)\])?\s*(.*?)\n- \*\*Result\*\*', block, re.DOTALL)
            result_match = re.search(r'- \*\*Result\*\*:\s*(.*?)\n>', block, re.DOTALL)
            
            if not all([trigger_match, action_match, result_match]):
                # Fallback to single-line parsing if the multi-line regex misses (e.g., missing blockquote)
                trigger_match = re.search(r'- \*\*Trigger\*\*:\s*(.*?)\n', block)
                action_match = re.search(r'- \*\*Action\*\*:\s*(?:\[(.*?)\])?\s*(.*?)\n', block)
                result_match = re.search(r'- \*\*Result\*\*:\s*(.*?)\n', block)
                
            if not all([trigger_match, action_match, result_match]):
                continue
                
            # Extract and replace newlines with a single space to construct a continuous string
            trigger_full_text = re.sub(r'\s*\n\s*', ' ', trigger_match.group(1).strip())
            action_concept_id = action_match.group(1).strip() if action_match.group(1) else ""
            action_text = re.sub(r'\s*\n\s*', ' ', action_match.group(2).strip())
            result_text = re.sub(r'\s*\n\s*', ' ', result_match.group(1).strip())
            
            # Extract explanation text
            explanation_match = re.search(r'> \*\*📝 해설.*?\n(.*)', block, re.DOTALL)
            explanation_text = ""
            explanation_html = ""
            if explanation_match:
                explanation_lines = explanation_match.group(1).strip().split('\n')
                explanation_lines = [line[2:] if line.startswith('> ') else (line[1:] if line.startswith('>') else line) for line in explanation_lines]
                explanation_text = '\n'.join(explanation_lines).strip()
                
                # HTML Pre-rendering (Dual-Column)
                temp_text = explanation_text
                math_dict = {}
                math_counter = 0
                
                def math_replacer(m):
                    nonlocal math_counter
                    token = f"XMATH{math_counter}X"
                    math_dict[token] = m.group(0)
                    math_counter += 1
                    return token
                
                # Extract math blocks
                temp_text = re.sub(r'(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$[^\$\n]+?\$|\\\([\s\S]*?\\\))', math_replacer, temp_text)
                
                # Render to HTML with nl2br
                parsed_html = markdown.markdown(temp_text, extensions=['extensions.nl2br' if markdown.__version__.startswith('2') else 'nl2br'])
                
                # Restore math blocks with HTML escaping
                for token, math_content in math_dict.items():
                    escaped_math = html.escape(math_content)
                    parsed_html = parsed_html.replace(token, escaped_math)
                
                # Sanitize with bleach
                allowed_tags = ['b', 'i', 'strong', 'em', 'ul', 'li', 'br', 'p', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote']
                explanation_html = bleach.clean(parsed_html, tags=allowed_tags)
            
            # Handling multi-triggers
            if '] + [' in trigger_full_text:
                raw_parts = trigger_full_text.split('] + [')
                trigger_parts = []
                for idx, p in enumerate(raw_parts):
                    p = p.strip()
                    # split('] + [') removes ] from non-last parts and [ from non-first parts
                    if idx < len(raw_parts) - 1:
                        p = p + ']'
                    if idx > 0:
                        p = '[' + p
                    trigger_parts.append(p)
            else:
                trigger_parts = [trigger_full_text.strip()]
            
            # Insert Step
            cursor.execute('''
                INSERT INTO steps (problem_id, step_number, step_title, explanation_text, explanation_html, action_concept_id, action_text, result_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (problem_id, step_num, step_title, explanation_text, explanation_html, action_concept_id, action_text, result_text))
            
            step_id = cursor.lastrowid
            
            # Insert Triggers and mapping (Result 트리거 제외)
            valid_trigger_inserted = False
            for t_text in trigger_parts:
                if is_result_trigger(t_text):
                    continue
                trigger_id = get_or_create_trigger(conn, t_text)
                cursor.execute('''
                    INSERT INTO step_triggers (step_id, trigger_id)
                    VALUES (?, ?)
                ''', (step_id, trigger_id))
                valid_trigger_inserted = True

            # 유효한 트리거가 없는 경우 step_title을 폴백 트리거로 사용
            if not valid_trigger_inserted and step_title:
                fallback_text = f'[{step_title}]'
                trigger_id = get_or_create_trigger(conn, fallback_text)
                cursor.execute('''
                    INSERT INTO step_triggers (step_id, trigger_id)
                    VALUES (?, ?)
                ''', (step_id, trigger_id))

    conn.commit()

def verify_db(conn):
    cursor = conn.cursor()
    
    print("\n--- DB Verification ---")
    
    cursor.execute('SELECT COUNT(*) FROM problems')
    print(f"Total Problems parsed: {cursor.fetchone()[0]} (Expected: 27)")
    
    cursor.execute('SELECT COUNT(*) FROM steps')
    print(f"Total Steps extracted: {cursor.fetchone()[0]}")
    
    cursor.execute('SELECT COUNT(*) FROM triggers')
    print(f"Total Unique Triggers: {cursor.fetchone()[0]}")
    
    print("\nTop 5 Action Concept IDs used:")
    cursor.execute('''
        SELECT action_concept_id, COUNT(*) as cnt 
        FROM steps 
        GROUP BY action_concept_id 
        ORDER BY cnt DESC 
        LIMIT 5
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} times")
        
    print("------------------------\n")

if __name__ == '__main__':
    conn = setup_database()
    load_concepts(conn)
    parse_solutions(conn)
    verify_db(conn)
    conn.close()
