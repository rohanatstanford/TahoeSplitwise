from db import get_connection

def calculate_balances():
    """
    Returns a dictionary of net balances for each user.
    Positive means they are owed money.
    Negative means they owe money.
    """
    conn = get_connection()
    c = conn.cursor()
    
    # Initialize balances
    c.execute('SELECT id, name FROM users')
    users = c.fetchall()
    balances = {u[0]: {"name": u[1], "net_balance": 0.0} for u in users}
    
    # Tally up expenses
    c.execute('''
        SELECT e.payer_id, es.user_id, es.amount_owed
        FROM expenses e
        JOIN expense_splits es ON e.id = es.expense_id
    ''')
    expense_details = c.fetchall()
    
    for payer_id, split_user_id, amount_owed in expense_details:
        if payer_id != split_user_id:
            # Payer is owed money
            balances[payer_id]["net_balance"] += amount_owed
            # Split user owes money
            balances[split_user_id]["net_balance"] -= amount_owed
            
    # Tally up settlements
    c.execute('SELECT payer_id, payee_id, amount FROM settlements')
    settlements = c.fetchall()
    
    for payer_id, payee_id, amount in settlements:
        # Payer reduces their debt (equivalent to increasing net balance)
        balances[payer_id]["net_balance"] += amount
        # Payee reduces amounts owed to them
        balances[payee_id]["net_balance"] -= amount
        
    conn.close()
    return balances

def simplify_debts(balances):
    """
    Takes the balance dictionary and returns a list of suggested transactions 
    to simplify debts.
    Returns: list of dicts {"from": user_id, "to": user_id, "amount": amount}
    """
    debtors = []
    creditors = []
    
    for user_id, data in balances.items():
        balance_amount = round(data["net_balance"], 2)
        if balance_amount < 0:
            debtors.append({"id": user_id, "name": data["name"], "amount": -balance_amount})
        elif balance_amount > 0:
            creditors.append({"id": user_id, "name": data["name"], "amount": balance_amount})
            
    # Sort them by amount descending
    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)
    
    transactions = []
    
    i = 0 # debtors index
    j = 0 # creditors index
    
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        
        amount = min(debtor["amount"], creditor["amount"])
        
        if amount > 0:
            transactions.append({
                "from_id": debtor["id"],
                "from_name": debtor["name"],
                "to_id": creditor["id"],
                "to_name": creditor["name"],
                "amount": amount
            })
            
        debtor["amount"] -= amount
        creditor["amount"] -= amount
        
        # Avoid floating point issues
        debtor["amount"] = round(debtor["amount"], 2)
        creditor["amount"] = round(creditor["amount"], 2)
        
        if debtor["amount"] == 0:
            i += 1
        if creditor["amount"] == 0:
            j += 1
            
    return transactions

def calculate_pairwise_balances():
    """
    Returns a 2D dictionary mapping user_id -> {other_user_id: net_amount_owed_to_user_id}.
    If matrix[A][B] = 50, it means B owes A $50.
    """
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT id FROM users')
    users = [row[0] for row in c.fetchall()]
    
    # Initialize matrix
    matrix = {u: {other: 0.0 for other in users} for u in users}
    
    c.execute('''
        SELECT e.payer_id, es.user_id, es.amount_owed
        FROM expenses e
        JOIN expense_splits es ON e.id = es.expense_id
    ''')
    expense_details = c.fetchall()
    
    for payer_id, split_user_id, amount_owed in expense_details:
        if payer_id != split_user_id:
            matrix[payer_id][split_user_id] += amount_owed
            
    c.execute('SELECT payer_id, payee_id, amount FROM settlements')
    settlements = c.fetchall()
    
    for payer_id, payee_id, amount in settlements:
        matrix[payee_id][payer_id] -= amount
        
    conn.close()
    
    net_matrix = {u: {other: 0.0 for other in users} for u in users}
    for u1 in users:
        for u2 in users:
            if u1 != u2:
                net_owed = matrix[u1][u2] - matrix[u2][u1]
                if net_owed > 0:
                    net_matrix[u1][u2] = net_owed
                    
    return net_matrix
