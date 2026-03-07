import streamlit as st
import pandas as pd
import io
from db import init_db, add_user, get_users, get_user_map, add_expense, get_expenses, add_settlement, get_settlements, update_expense, delete_expense, clear_all_expenses, clear_all_users, delete_user
from logic import calculate_balances, simplify_debts, calculate_pairwise_balances

# Initialize database
init_db()

st.set_page_config(page_title="Tahoe Splitwise", layout="wide")

st.title("🏔️ Tahoe Splitwise")
# st.markdown("Split expenses and settle debts for your Tahoe trip.")

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if not st.session_state.current_user:
    st.subheader("Login")
    users = get_users()
    if users:
        user_id = st.selectbox("Select user to log in:", options=[u["id"] for u in users], format_func=lambda x: get_user_map()[x])
        if st.button("Log In"):
            st.session_state.current_user = {"id": user_id, "name": get_user_map()[user_id]}
            st.rerun()
    else:
        st.info("No users found. Please create one to begin.")
    
    st.divider()
    st.subheader("Or Add New User")
    # st.write("*(Type 'Admin' here to access Admin controls)*")
    with st.form("login_add_user"):
        new_name = st.text_input("Name")
        if st.form_submit_button("Add & Log In"):
            name_clean = new_name.strip()
            if name_clean.lower() == 'admin':
                st.session_state.current_user = {"id": -1, "name": "Admin"}
                st.rerun()
            elif name_clean:
                if add_user(name_clean):
                    map_inv = {v:k for k,v in get_user_map().items()}
                    new_id = map_inv.get(name_clean)
                    if new_id:
                        st.session_state.current_user = {"id": new_id, "name": name_clean}
                    st.success(f"Added {name_clean}!")
                    st.rerun()
                else:
                    st.error("That name already exists.")
            else:
                st.warning("Please enter a name.")
    st.stop()
else:
    st.sidebar.write(f"Logged in as: **{st.session_state.current_user['name']}**")
    if st.sidebar.button("Log Out"):
        st.session_state.current_user = None
        st.rerun()

    if st.session_state.current_user['name'].lower() == 'admin':
        st.sidebar.divider()
        st.sidebar.write("👑 **Admin Controls**")
        if st.sidebar.button("Clear All Expenses"):
            if clear_all_expenses():
                st.sidebar.success("All expenses & settlements cleared!")
            else:
                st.sidebar.error("Failed to clear expenses.")
            st.rerun()
            
        if st.sidebar.button("Clear All Users & Data"):
            if clear_all_users():
                st.session_state.current_user = None
                st.sidebar.success("All data wiped!")
            else:
                st.sidebar.error("Failed to wipe data.")
            st.rerun()
            
        st.sidebar.divider()
        st.sidebar.write("👤 **Remove Specific Person**")
        all_users = get_users()
        if all_users:
            user_to_delete = st.sidebar.selectbox("Select user to remove:", options=[u["id"] for u in all_users], format_func=lambda x: get_user_map()[x], key="del_user_select")
            if st.sidebar.button("Remove User", key="del_user_btn"):
                if delete_user(user_to_delete):
                    st.sidebar.success("User and their data removed!")
                    if st.session_state.current_user['id'] == user_to_delete:
                        st.session_state.current_user = None
                    st.rerun()
                else:
                    st.sidebar.error("Failed to remove user.")
        else:
            st.sidebar.info("No users to remove.")

tabs = st.tabs(["Dashboard", "Add Expense", "Settle Up", "Manage Group", "History", "All Expenses"])

# --- Manage Group Tab ---
with tabs[3]:
    st.header("Manage Group")
    st.write("Add people to your Tahoe trip.")
    
    with st.form("add_user_form", clear_on_submit=True):
        new_name = st.text_input("Name")
        submit_user = st.form_submit_button("Add Person")
        
        if submit_user:
            if new_name.strip():
                if add_user(new_name.strip()):
                    st.success(f"Added {new_name.strip()}!")
                    st.rerun()
                else:
                    st.error("That name already exists.")
            else:
                st.warning("Please enter a name.")
                
    st.subheader("Current Group Members")
    users = get_users()
    if users:
        for u in users:
            st.write(f"- {u['name']}")
    else:
        st.info("No members added yet.")

# Ensure we have users before rendering other complex forms
users = get_users()
user_map = get_user_map()

# --- Add Expense Tab ---
with tabs[1]:
    st.header("Add a New Expense")
    
    if not users:
        st.warning("Please add people to the group first.")
    else:
        with st.form("add_expense_form", clear_on_submit=True):
            description = st.text_input("Description (e.g., Groceries, Ski Passes)")
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
            
            payer_id = st.selectbox(
                "Who paid?", 
                options=[u["id"] for u in users], 
                format_func=lambda x: user_map[x],
                index=[u["id"] for u in users].index(st.session_state.current_user['id']) if st.session_state.current_user['id'] in [u["id"] for u in users] else 0
            )
            
            split_with = st.multiselect(
                "Split among:", 
                options=[u["id"] for u in users],
                default=[u["id"] for u in users],
                format_func=lambda x: user_map[x]
            )
            
            is_custom_split = st.checkbox("Split unequally", value=False)
            
            custom_amounts = {}
            if is_custom_split and split_with:
                st.write("Enter amounts for each person (must sum to total):")
                for uid in split_with:
                    custom_amounts[uid] = st.number_input(f"Amount for {user_map[uid]}", min_value=0.0, step=0.01, format="%.2f", key=f"split_add_{uid}")
            
            submit_expense = st.form_submit_button("Save Expense")
            
            if submit_expense:
                if not description.strip():
                    st.error("Please provide a description.")
                elif not split_with:
                    st.error("You must select at least one person to split the expense with.")
                else:
                    splits = []
                    valid = True
                    if is_custom_split:
                        total_custom = sum(custom_amounts.values())
                        if abs(total_custom - amount) > 0.01:
                            st.error(f"Custom amounts sum to ${total_custom:.2f}, but the total is ${amount:.2f}. Please adjust.")
                            valid = False
                        else:
                            for uid in split_with:
                                splits.append({"user_id": uid, "amount_owed": custom_amounts[uid]})
                    else:
                        split_amt = amount / len(split_with)
                        for uid in split_with:
                            splits.append({"user_id": uid, "amount_owed": split_amt})
                    
                    if valid:
                        success = add_expense(description.strip(), amount, payer_id, splits)
                        if success:
                            st.success(f"Added expense: {description}")
                            st.rerun()
                        else:
                            st.error("Failed to add expense.")

# --- Settle Up Tab ---
with tabs[2]:
    st.header("Settle Up")
    st.write("Record a payment from one person to another.")
    
    if len(users) < 2:
        st.warning("Need at least two people to settle up.")
    else:
        with st.form("settlement_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                payer_id = st.selectbox(
                    "Who is paying?", 
                    options=[u["id"] for u in users], 
                    format_func=lambda x: user_map[x],
                    key="settle_payer"
                )
            with col2:
                payee_id = st.selectbox(
                    "Who are they paying?", 
                    options=[u["id"] for u in users], 
                    format_func=lambda x: user_map[x],
                    key="settle_payee"
                )
                
            amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f", key="settle_amount")
            
            submit_settlement = st.form_submit_button("Record Payment")
            
            if submit_settlement:
                if payer_id == payee_id:
                    st.error("A person cannot settle up with themselves.")
                else:
                    success = add_settlement(payer_id, payee_id, amount)
                    if success:
                        st.success(f"Recorded payment of ${amount:.2f} from {user_map[payer_id]} to {user_map[payee_id]}")
                        st.rerun()
                    else:
                        st.error("Failed to record settlement.")

# --- Dashboard Tab ---
with tabs[0]:
    st.header("Dashboard")
    
    if not users:
        st.info("Add some members and expenses to see the dashboard!")
    else:
        balances = calculate_balances()
        
        st.subheader("Current Balances")
        # Display nicely formatted balances
        balance_data = []
        for uid, data in balances.items():
            if data['name'] != 'Admin':
                b = data["net_balance"]
                status = "Settled Up"
                color = "gray"
                if b > 0:
                    status = f"Gets back ${b:.2f}"
                    color = "green"
                elif b < 0:
                    status = f"Owes ${-b:.2f}"
                    color = "red"
                    
                balance_data.append({
                    "Person": data["name"],
                    "Balance": status,
                    "_raw_balance": b
                })
                
                st.markdown(f"**{data['name']}**: :{color}[{status}]")
            
        st.divider()
        st.subheader("Suggested Payments to Settle All Debts")
        transactions = simplify_debts(balances)
        
        if not transactions:
            st.success("Everyone is settled up! 🎉")
        else:
            for t in transactions:
                st.info(f"💸 **{t['from_name']}** pays **{t['to_name']}** ${t['amount']:.2f}")

        st.divider()
        st.subheader("Debt Matrix")
        st.write("Detailed breakdown of who owes whom:")
        pairwise = calculate_pairwise_balances()
        
        matrix_data = []
        for u_owes in users:
            row = {"Person Who Owes": u_owes["name"]}
            for u_owed in users:
                if u_owes["id"] == u_owed["id"]:
                    row[u_owed["name"]] = "-"
                else:
                    val = pairwise[u_owed['id']][u_owes['id']]
                    row[u_owed["name"]] = f"${val:.2f}" if val > 0 else "-"
            matrix_data.append(row)

        df_matrix = pd.DataFrame(matrix_data)
        st.dataframe(df_matrix, hide_index=True, use_container_width=True)

# --- History Tab ---
with tabs[4]:
    st.header("History")
    
    st.subheader("Expenses")
    expenses = get_expenses()
    if expenses:
        for e in expenses:
            with st.expander(f"{e['description']} - ${e['amount']:.2f} (Paid by {e['payer_name']}) - {e['date'][:10]}"):
                for split in e['splits']:
                    st.write(f"- {split['name']} owes ${split['amount_owed']:.2f}")
                    
                is_admin = st.session_state.current_user['name'].lower() == 'admin'
                if e['payer_id'] == st.session_state.current_user['id'] or is_admin:
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Edit Expense", key=f"edit_btn_{e['id']}"):
                            st.session_state.editing_expense_id = e['id']
                            st.rerun()
                    with col2:
                        if st.button("Delete Expense", key=f"del_btn_{e['id']}"):
                            delete_expense(e['id'])
                            st.success("Deleted!")
                            st.rerun()
                            
                    if st.session_state.get("editing_expense_id") == e['id']:
                        st.write("---")
                        st.write("Edit Expense")
                        with st.form(f"edit_form_{e['id']}"):
                            new_desc = st.text_input("Description", value=e['description'])
                            new_amount = st.number_input("Amount ($)", value=float(e['amount']), min_value=0.01, step=0.01)
                            new_splits = st.multiselect(
                                "Split among:", 
                                options=[u["id"] for u in users],
                                default=[s["id"] for s in e['splits']],
                                format_func=lambda x: user_map[x]
                            )
                            
                            is_custom_split_edit = st.checkbox("Split unequally", value=False, key=f"custom_edit_{e['id']}")
                            custom_amounts_edit = {}
                            if is_custom_split_edit and new_splits:
                                st.write("Enter amounts for each person:")
                                for s in e['splits']:
                                    if s["id"] in new_splits:
                                        custom_amounts_edit[s["id"]] = st.number_input(f"Amount for {s['name']}", min_value=0.0, step=0.01, format="%.2f", value=float(s["amount_owed"]), key=f"split_edit_{e['id']}_{s['id']}")
                                for uid in new_splits:
                                    if uid not in custom_amounts_edit:
                                        custom_amounts_edit[uid] = st.number_input(f"Amount for {user_map[uid]}", min_value=0.0, step=0.01, format="%.2f", value=0.0, key=f"split_edit_{e['id']}_{uid}")

                            col_sub1, col_sub2 = st.columns(2)
                            with col_sub1:
                                save_edit = st.form_submit_button("Save Changes")
                            with col_sub2:
                                cancel_edit = st.form_submit_button("Cancel")
                                
                            if save_edit:
                                if not new_desc.strip():
                                    st.error("Description required.")
                                elif not new_splits:
                                    st.error("Select at least one person.")
                                else:
                                    splits_to_save = []
                                    valid_edit = True
                                    if is_custom_split_edit:
                                        total_custom_edit = sum(custom_amounts_edit.values())
                                        if abs(total_custom_edit - new_amount) > 0.01:
                                            st.error(f"Custom amounts sum to ${total_custom_edit:.2f}, but the total is ${new_amount:.2f}. Please adjust.")
                                            valid_edit = False
                                        else:
                                            for uid in new_splits:
                                                splits_to_save.append({"user_id": uid, "amount_owed": custom_amounts_edit[uid]})
                                    else:
                                        split_amt = new_amount / len(new_splits)
                                        for uid in new_splits:
                                            splits_to_save.append({"user_id": uid, "amount_owed": split_amt})

                                    if valid_edit:
                                        update_expense(e['id'], new_desc.strip(), new_amount, e['payer_id'], splits_to_save)
                                        st.session_state.editing_expense_id = None
                                        st.success("Updated!")
                                        st.rerun()
                            if cancel_edit:
                                st.session_state.editing_expense_id = None
                                st.rerun()
    else:
        st.write("No expenses recorded yet.")
        
    st.divider()
    
    st.subheader("Settlements")
    settlements = get_settlements()
    if settlements:
        for s in settlements:
            st.write(f"💵 **{s['payer_name']}** paid **${s['amount']:.2f}** to **{s['payee_name']}** on {s['date'][:10]}")
    else:
        st.write("No settlements recorded yet.")

# --- All Expenses Table Tab ---
with tabs[5]:
    st.header("All Expenses")
    expenses_data = get_expenses()
    
    if not expenses_data:
        st.info("No expenses found.")
    else:
        # Build tabular data
        table_data = []
        for e in expenses_data:
            split_names = [s['name'] for s in e['splits']]
            table_data.append({
                "Date": e['date'][:10],
                "Description": e['description'],
                "Amount ($)": round(float(e['amount']), 2),
                "Payer": e['payer_name'],
                "Shared With": ", ".join(split_names)
            })
            
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
        
        # Export button
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Expenses')
            
            # Formats
            workbook = writer.book
            worksheet = writer.sheets['Expenses']
            money_format = workbook.add_format({'num_format': '$#,##0.00'})
            
            # Set money format and reasonable column widths
            worksheet.set_column('A:A', 12)  # Date
            worksheet.set_column('B:B', 30)  # Description
            worksheet.set_column('C:C', 12, money_format)  # Amount
            worksheet.set_column('D:D', 15)  # Payer
            worksheet.set_column('E:E', 40)  # Shared With

        st.download_button(
            label="⬇️ Download Excel",
            data=buffer.getvalue(),
            file_name="tahoe_expenses.xlsx",
            mime="application/vnd.ms-excel",
            type="primary"
        )
