from db import get_users, get_expenses, get_settlements

def calculate_balances():
    users = get_users()
    balances = {u["id"]: {"name": u["name"], "net_balance": 0.0} for u in users}
    
    expenses = get_expenses()
    for e in expenses:
        payer_id = e["payer_id"]
        if payer_id not in balances:
            balances[payer_id] = {"name": e["payer_name"], "net_balance": 0.0}
            
        for split in e["splits"]:
            split_user_id = split["id"]
            amount_owed = split["amount_owed"]
            
            if split_user_id not in balances:
                balances[split_user_id] = {"name": split["name"], "net_balance": 0.0}
                
            if payer_id != split_user_id:
                balances[payer_id]["net_balance"] += amount_owed
                balances[split_user_id]["net_balance"] -= amount_owed
                
    settlements = get_settlements()
    for s in settlements:
        payer_id = s["payer_id"]
        payee_id = s["payee_id"]
        amount = s["amount"]
        
        if payer_id not in balances:
            balances[payer_id] = {"name": s["payer_name"], "net_balance": 0.0}
        if payee_id not in balances:
            balances[payee_id] = {"name": s["payee_name"], "net_balance": 0.0}
            
        balances[payer_id]["net_balance"] += amount
        balances[payee_id]["net_balance"] -= amount
        
    return balances

def simplify_debts(balances):
    debtors = []
    creditors = []
    
    for user_id, data in balances.items():
        if data["name"] == "Admin": continue
        balance_amount = round(data["net_balance"], 2)
        if balance_amount < 0:
            debtors.append({"id": user_id, "name": data["name"], "amount": -balance_amount})
        elif balance_amount > 0:
            creditors.append({"id": user_id, "name": data["name"], "amount": balance_amount})
            
    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)
    
    transactions = []
    
    i = 0
    j = 0
    
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
        
        debtor["amount"] = round(debtor["amount"], 2)
        creditor["amount"] = round(creditor["amount"], 2)
        
        if debtor["amount"] == 0:
            i += 1
        if creditor["amount"] == 0:
            j += 1
            
    return transactions

def calculate_pairwise_balances():
    users = get_users()
    user_ids = [u["id"] for u in users]
    matrix = {u: {other: 0.0 for other in user_ids} for u in user_ids}
    
    expenses = get_expenses()
    for e in expenses:
        payer_id = e["payer_id"]
        if payer_id not in matrix:
            user_ids.append(payer_id)
            matrix[payer_id] = {other: 0.0 for other in user_ids}
            for u in user_ids:
                if payer_id not in matrix[u]:
                    matrix[u][payer_id] = 0.0

        for split in e["splits"]:
            split_user_id = split["id"]
            amount_owed = split["amount_owed"]
            
            if split_user_id not in matrix:
                user_ids.append(split_user_id)
                matrix[split_user_id] = {other: 0.0 for other in user_ids}
                for u in user_ids:
                    if split_user_id not in matrix[u]:
                        matrix[u][split_user_id] = 0.0
                        
            if payer_id != split_user_id:
                matrix[payer_id][split_user_id] += amount_owed

    settlements = get_settlements()
    for s in settlements:
        payer_id = s["payer_id"]
        payee_id = s["payee_id"]
        amount = s["amount"]
        
        for u in [payer_id, payee_id]:
            if u not in matrix:
                user_ids.append(u)
                matrix[u] = {other: 0.0 for other in user_ids}
                for uid in user_ids:
                    if u not in matrix[uid]:
                        matrix[uid][u] = 0.0
                        
        matrix[payee_id][payer_id] -= amount
        
    net_matrix = {u: {other: 0.0 for other in user_ids} for u in user_ids}
    for u1 in user_ids:
        for u2 in user_ids:
            if u1 != u2:
                net_owed = matrix[u1][u2] - matrix[u2][u1]
                if net_owed > 0:
                    net_matrix[u1][u2] = net_owed
                    
    return net_matrix
