import sqlite3
import json

DB_FILE = 'kice_database.sqlite'
MAPPING_FILE = 'trigger_mapping.json'

def update_db_with_mappings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    updated_count = 0
    for item in data:
        trigger_id = item['trigger_id']
        normalized_text = item['normalized_text']
        
        if normalized_text:
            cursor.execute('''
                UPDATE triggers 
                SET normalized_text = ? 
                WHERE trigger_id = ?
            ''', (normalized_text, trigger_id))
            updated_count += 1
            
    conn.commit()
    print(f"Successfully updated {updated_count} triggers in the database with their normalized texts.")
    
    # Print a distinct list of normalized texts to see the grouping effect
    cursor.execute('SELECT normalized_text, COUNT(*) FROM triggers WHERE normalized_text != "" GROUP BY normalized_text ORDER BY COUNT(*) DESC')
    print("\n--- Normalized Trigger Distribution ---")
    for row in cursor.fetchall():
        print(f"[{row[1]} times] {row[0]}")
        
    conn.close()

if __name__ == '__main__':
    update_db_with_mappings()
