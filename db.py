import gspread
from google.oauth2.service_account import Credentials
import os
import time
from datetime import datetime
import streamlit as st

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
SHEET_ID = '154n7Afm0qQEuvkn_5dt7lYhDsSrBdZYu4WnsV6oFRPY'

_client = None
_sheet = None
_worksheets = {}

def get_client():
    global _client
    if _client is None:
        if os.path.exists(CREDENTIALS_FILE):
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        else:
            # Fallback to streamlit secrets when deployed
            import json
            secrets_val = st.secrets["gcp_service_account"]
            
            # If the user pasted it as a raw string in Streamlit Secrets
            if isinstance(secrets_val, str):
                creds_data = json.loads(secrets_val)
            else:
                # If they pasted it as a TOML dictionary
                creds_data = dict(secrets_val)
                if "private_key" in creds_data:
                    # Ensure literal string \n are parsed as actual newlines
                    creds_data["private_key"] = creds_data["private_key"].replace("\\n", "\n")
            
            creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            
        _client = gspread.authorize(creds)
    return _client

def get_sheet():
    global _sheet
    if _sheet is None:
        _sheet = get_client().open_by_key(SHEET_ID)
    return _sheet

def get_worksheet(name, headers=None):
    global _worksheets
    if name in _worksheets:
        return _worksheets[name]
    sheet = get_sheet()
    try:
        ws = sheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows="1000", cols="20")
        if headers:
            ws.append_row(headers)
    _worksheets[name] = ws
    return ws

def init_db():
    get_worksheet('users', ['id', 'name'])
    get_worksheet('expenses', ['id', 'description', 'amount', 'payer_id', 'date'])
    get_worksheet('expense_splits', ['id', 'expense_id', 'user_id', 'amount_owed'])
    get_worksheet('settlements', ['id', 'payer_id', 'payee_id', 'amount', 'date'])

def generate_id():
    return int(time.time() * 1000000 % 2147483647)

def add_user(name):
    ws = get_worksheet('users')
    records = ws.get_all_records()
    if any(str(r.get('name', '')).lower() == name.lower() for r in records):
        return False
    new_id = generate_id()
    ws.append_row([str(new_id), name])
    st.cache_data.clear()
    return True

@st.cache_data(ttl=10)
def get_users():
    ws = get_worksheet('users')
    records = ws.get_all_records()
    users = [{"id": int(r['id']), "name": str(r['name'])} for r in records if r.get('id') and str(r.get('name', '')).lower() != 'admin']
    return sorted(users, key=lambda x: x['name'])

@st.cache_data(ttl=10)
def get_user_map():
    users = get_users()
    m = {}
    for u in users:
        m[u["id"]] = u["name"]
    return m

def add_expense(description, amount, payer_id, splits):
    try:
        exp_ws = get_worksheet('expenses')
        splits_ws = get_worksheet('expense_splits')
        
        expense_id = generate_id()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        exp_ws.append_row([str(expense_id), description, str(amount), str(payer_id), date_str])
        
        rows_to_insert = []
        for split in splits:
            split_id = generate_id()
            rows_to_insert.append([str(split_id), str(expense_id), str(split["user_id"]), str(split["amount_owed"])])
            time.sleep(0.01)
        
        if rows_to_insert:
            splits_ws.append_rows(rows_to_insert)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error adding expense: {e}")
        return False

@st.cache_data(ttl=10)
def get_expenses():
    exp_ws = get_worksheet('expenses')
    splits_ws = get_worksheet('expense_splits')
    
    users_records = get_worksheet('users').get_all_records()
    all_users_map = {int(u['id']): str(u['name']) for u in users_records if u.get('id')}
    
    expenses_data = exp_ws.get_all_records()
    splits_data = splits_ws.get_all_records()
    
    expenses_data.sort(key=lambda x: str(x.get('date', '')), reverse=True)
    
    result = []
    for row in expenses_data:
        if not row.get('id'): continue
        expense_id = int(row['id'])
        payer_id = int(row['payer_id'])
        payer_name = all_users_map.get(payer_id, "Unknown")
        
        expense_splits = [s for s in splits_data if s.get('expense_id') and int(s['expense_id']) == expense_id]
        
        formatted_splits = []
        for s in expense_splits:
            uid = int(s['user_id'])
            uname = all_users_map.get(uid, "Unknown")
            formatted_splits.append({
                "id": uid,
                "name": uname,
                "amount_owed": float(s['amount_owed'])
            })
            
        result.append({
            "id": expense_id,
            "description": str(row['description']),
            "amount": float(row['amount']),
            "payer_name": payer_name,
            "date": str(row['date']),
            "payer_id": payer_id,
            "splits": formatted_splits
        })
        
    return result

def add_settlement(payer_id, payee_id, amount):
    try:
        ws = get_worksheet('settlements')
        settlement_id = generate_id()
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([str(settlement_id), str(payer_id), str(payee_id), str(amount), date_str])
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error adding settlement: {e}")
        return False

@st.cache_data(ttl=10)
def get_settlements():
    ws = get_worksheet('settlements')
    users_records = get_worksheet('users').get_all_records()
    all_users_map = {int(u['id']): str(u['name']) for u in users_records if u.get('id')}
    
    settlements = ws.get_all_records()
    settlements.sort(key=lambda x: str(x.get('date', '')), reverse=True)
    
    result = []
    for row in settlements:
        if not row.get('id'): continue
        payer_id = int(row['payer_id'])
        payee_id = int(row['payee_id'])
        result.append({
            "id": int(row['id']),
            "payer_id": payer_id,
            "payee_id": payee_id,
            "payer_name": all_users_map.get(payer_id, "Unknown"),
            "payee_name": all_users_map.get(payee_id, "Unknown"),
            "amount": float(row['amount']),
            "date": str(row['date'])
        })
    return result

def update_expense(expense_id, description, amount, payer_id, splits):
    try:
        exp_ws = get_worksheet('expenses')
        splits_ws = get_worksheet('expense_splits')
        
        exp_records = exp_ws.get_all_records()
        row_idx = None
        for i, r in enumerate(exp_records):
            if r.get('id') and int(r['id']) == int(expense_id):
                row_idx = i + 2
                break
                
        if row_idx is not None:
            exp_ws.update(range_name=f"B{row_idx}:D{row_idx}", values=[[description, str(amount), str(payer_id)]])
            
            all_splits = splits_ws.get_all_values()
            rows_to_delete = []
            for i, row in enumerate(all_splits):
                if i == 0: continue
                if row[1] and str(row[1]).isdigit() and int(row[1]) == int(expense_id):
                    rows_to_delete.append(i + 1)
            
            for r_idx in sorted(rows_to_delete, reverse=True):
                splits_ws.delete_rows(r_idx)
                
            rows_to_insert = []
            for split in splits:
                split_id = generate_id()
                rows_to_insert.append([str(split_id), str(expense_id), str(split["user_id"]), str(split["amount_owed"])])
                time.sleep(0.01)
                
            if rows_to_insert:
                splits_ws.append_rows(rows_to_insert)
                
            st.cache_data.clear()
            return True
        return False
    except Exception as e:
        print(f"Error updating expense: {e}")
        return False

def delete_expense(expense_id):
    try:
        exp_ws = get_worksheet('expenses')
        splits_ws = get_worksheet('expense_splits')
        
        all_splits = splits_ws.get_all_values()
        rows_to_delete = []
        for i, row in enumerate(all_splits):
            if i == 0: continue
            if row[1] and str(row[1]).isdigit() and int(row[1]) == int(expense_id):
                rows_to_delete.append(i + 1)
        for r_idx in sorted(rows_to_delete, reverse=True):
            splits_ws.delete_rows(r_idx)
            
        all_exps = exp_ws.get_all_values()
        exp_row_to_delete = None
        for i, row in enumerate(all_exps):
            if i == 0: continue
            if row[0] and str(row[0]).isdigit() and int(row[0]) == int(expense_id):
                exp_row_to_delete = i + 1
                break
        
        if exp_row_to_delete:
            exp_ws.delete_rows(exp_row_to_delete)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error deleting expense: {e}")
        return False

def clear_all_expenses():
    try:
        def reset_sheet(name, headers):
            ws = get_worksheet(name)
            ws.clear()
            ws.append_row(headers)
            
        reset_sheet('expense_splits', ['id', 'expense_id', 'user_id', 'amount_owed'])
        reset_sheet('expenses', ['id', 'description', 'amount', 'payer_id', 'date'])
        reset_sheet('settlements', ['id', 'payer_id', 'payee_id', 'amount', 'date'])
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error clearing expenses: {e}")
        return False

def clear_all_users():
    try:
        clear_all_expenses()
        ws = get_worksheet('users')
        ws.clear()
        ws.append_row(['id', 'name'])
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error clearing users: {e}")
        return False

def delete_user(user_id):
    try:
        exp_ws = get_worksheet('expenses')
        splits_ws = get_worksheet('expense_splits')
        settlements_ws = get_worksheet('settlements')
        users_ws = get_worksheet('users')
        
        all_exps = exp_ws.get_all_values()
        user_expense_ids = []
        exp_rows_to_delete = []
        for i, row in enumerate(all_exps):
            if i == 0: continue
            if row[3] and str(row[3]).isdigit() and int(row[3]) == int(user_id):
                user_expense_ids.append(int(row[0]))
                exp_rows_to_delete.append(i + 1)
                
        all_splits = splits_ws.get_all_values()
        split_rows_to_delete = []
        for i, row in enumerate(all_splits):
            if i == 0: continue
            if row[1] and str(row[1]).isdigit() and int(row[1]) in user_expense_ids:
                split_rows_to_delete.append(i + 1)
            elif row[2] and str(row[2]).isdigit() and int(row[2]) == int(user_id):
                if (i+1) not in split_rows_to_delete:
                    split_rows_to_delete.append(i + 1)
                
        all_sets = settlements_ws.get_all_values()
        set_rows_to_delete = []
        for i, row in enumerate(all_sets):
            if i == 0: continue
            if (row[1] and str(row[1]).isdigit() and int(row[1]) == int(user_id)) or \
               (row[2] and str(row[2]).isdigit() and int(row[2]) == int(user_id)):
                set_rows_to_delete.append(i + 1)
                
        all_users = users_ws.get_all_values()
        user_rows_to_delete = []
        for i, row in enumerate(all_users):
            if i == 0: continue
            if row[0] and str(row[0]).isdigit() and int(row[0]) == int(user_id):
                user_rows_to_delete.append(i+1)
                
        for r_idx in sorted(split_rows_to_delete, reverse=True):
            splits_ws.delete_rows(r_idx)
        for r_idx in sorted(exp_rows_to_delete, reverse=True):
            exp_ws.delete_rows(r_idx)
        for r_idx in sorted(set_rows_to_delete, reverse=True):
            settlements_ws.delete_rows(r_idx)
        for r_idx in sorted(user_rows_to_delete, reverse=True):
            users_ws.delete_rows(r_idx)
            
        st.cache_data.clear()
        return True
    except Exception as e:
        print(f"Error deleting user: {e}")
        return False
