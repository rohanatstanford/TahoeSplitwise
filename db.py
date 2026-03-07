import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'tahoe_costing.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    
    # Expenses table
    c.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payer_id INTEGER NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (payer_id) REFERENCES users (id)
        )
    ''')
    
    # Expense splits table
    c.execute('''
        CREATE TABLE IF NOT EXISTS expense_splits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount_owed REAL NOT NULL,
            FOREIGN KEY (expense_id) REFERENCES expenses (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Settlements table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payer_id INTEGER NOT NULL,
            payee_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (payer_id) REFERENCES users (id),
            FOREIGN KEY (payee_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Helper functions for db operations
def add_user(name):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (name) VALUES (?)', (name,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT id, name FROM users ORDER BY name')
    users = c.fetchall()
    conn.close()
    return [{"id": row[0], "name": row[1]} for row in users if row[1].lower() != 'admin']

def get_user_map():
    users = get_users()
    return {u["id"]: u["name"] for u in users}

def add_expense(description, amount, payer_id, splits):
    conn = get_connection()
    c = conn.cursor()
    try:
        # Insert expense
        c.execute('''
            INSERT INTO expenses (description, amount, payer_id)
            VALUES (?, ?, ?)
        ''', (description, amount, payer_id))
        expense_id = c.lastrowid
        
        # Insert splits
        for split in splits:
            c.execute('''
                INSERT INTO expense_splits (expense_id, user_id, amount_owed)
                VALUES (?, ?, ?)
            ''', (expense_id, split["user_id"], split["amount_owed"]))
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding expense: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_expenses():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT e.id, e.description, e.amount, u.name as payer_name, e.date, e.payer_id
        FROM expenses e
        JOIN users u ON e.payer_id = u.id
        ORDER BY e.date DESC
    ''')
    expenses = c.fetchall()
    
    result = []
    for row in expenses:
        expense_id = row[0]
        c.execute('''
            SELECT u.id, u.name, es.amount_owed 
            FROM expense_splits es
            JOIN users u ON es.user_id = u.id
            WHERE es.expense_id = ?
        ''', (expense_id,))
        splits = c.fetchall()
        
        result.append({
            "id": row[0],
            "description": row[1],
            "amount": row[2],
            "payer_name": row[3],
            "date": row[4],
            "payer_id": row[5],
            "splits": [{"id": s[0], "name": s[1], "amount_owed": s[2]} for s in splits]
        })
        
    conn.close()
    return result

def add_settlement(payer_id, payee_id, amount):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO settlements (payer_id, payee_id, amount)
            VALUES (?, ?, ?)
        ''', (payer_id, payee_id, amount))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding settlement: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_settlements():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT s.id, payer.name, payee.name, s.amount, s.date
        FROM settlements s
        JOIN users payer ON s.payer_id = payer.id
        JOIN users payee ON s.payee_id = payee.id
        ORDER BY s.date DESC
    ''')
    settlements = c.fetchall()
    conn.close()
    return [{"id": row[0], "payer_name": row[1], "payee_name": row[2], "amount": row[3], "date": row[4]} for row in settlements]

def update_expense(expense_id, description, amount, payer_id, splits):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('''
            UPDATE expenses 
            SET description = ?, amount = ?, payer_id = ?
            WHERE id = ?
        ''', (description, amount, payer_id, expense_id))
        
        c.execute('DELETE FROM expense_splits WHERE expense_id = ?', (expense_id,))
        
        for split in splits:
            c.execute('''
                INSERT INTO expense_splits (expense_id, user_id, amount_owed)
                VALUES (?, ?, ?)
            ''', (expense_id, split["user_id"], split["amount_owed"]))
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating expense: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_expense(expense_id):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM expense_splits WHERE expense_id = ?', (expense_id,))
        c.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting expense: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def clear_all_expenses():
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM expense_splits')
        c.execute('DELETE FROM expenses')
        c.execute('DELETE FROM settlements')
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing expenses: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def clear_all_users():
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM expense_splits')
        c.execute('DELETE FROM expenses')
        c.execute('DELETE FROM settlements')
        c.execute('DELETE FROM users')
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM expense_splits WHERE expense_id IN (SELECT id FROM expenses WHERE payer_id = ?)', (user_id,))
        c.execute('DELETE FROM expenses WHERE payer_id = ?', (user_id,))
        c.execute('DELETE FROM expense_splits WHERE user_id = ?', (user_id,))
        c.execute('DELETE FROM settlements WHERE payer_id = ? OR payee_id = ?', (user_id, user_id))
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting user: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
