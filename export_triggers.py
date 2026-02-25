import sqlite3
import json

DB_FILE = 'kice_database.sqlite'
MAPPING_FILE = 'trigger_mapping.json'

def export_triggers():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Select all triggers that don't have a normalized text yet
    cursor.execute('SELECT trigger_id, trigger_text, normalized_text FROM triggers ORDER BY trigger_id')
    rows = cursor.fetchall()
    
    mapping_data = []
    for row in rows:
        mapping_data.append({
            "trigger_id": row[0],
            "trigger_text": row[1],
            "normalized_text": row[2] if row[2] else ""  # Leave blank for manual filling
        })
        
    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping_data, f, ensure_ascii=False, indent=4)
        
    print(f"Successfully exported {len(mapping_data)} triggers to {MAPPING_FILE}")
    conn.close()

if __name__ == '__main__':
    export_triggers()
