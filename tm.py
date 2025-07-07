# === INSTALL THESE FIRST ===
# pip install streamlit firebase-admin bcrypt

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import bcrypt
from datetime import datetime, date, time
from PIL import Image
import io
import base64
from google.oauth2 import service_account
import json

# === FIREBASE INITIALIZATION ===
from firebase_admin import credentials

if not firebase_admin._apps:
    cred = credentials.Certificate(dict(st.secrets["firebase"]))
    firebase_admin.initialize_app(cred)

# === LOGO & TITLE ===
def get_base64_of_image(path):
    with open(path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode()

logo_base64 = get_base64_of_image("logo.png")

st.markdown(f"""
    <div style='text-align: center;'>
        <img src="data:image/png;base64,{logo_base64}" width="200"/>
        <h2 style='margin-top: 10px;'>Task Board v1</h2>
    </div>
""", unsafe_allow_html=True)

st.divider()


# === FIRESTORE COLLECTIONS ===
USERS_COLLECTION = "users"
TASKS_COLLECTION = "tasks"

# === AUTH & DB HELPERS ===
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def register_user(username, password, first_name, last_name, role="employee", manager_id=""):
    users_ref = db.collection(USERS_COLLECTION)
    if users_ref.document(username).get().exists:
        return False
    users_ref.document(username).set({
        "username": username,
        "password_hash": hash_password(password),
        "first_name": first_name,
        "last_name": last_name,
        "role": role,
        "manager_id": manager_id
    })
    return True

def login(username, password):
    user_doc = db.collection(USERS_COLLECTION).document(username).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        if check_password(password, user_data["password_hash"]):
            return user_data
    return None

def get_all_users(role_filter=None, manager_id=None):
    users = db.collection(USERS_COLLECTION).stream()
    user_data = []
    for user in users:
        data = user.to_dict()
        if (role_filter is None or data.get("role") == role_filter) and (manager_id is None or data.get("manager_id") == manager_id):
            user_data.append(data)
    return user_data

def get_all_usernames(role_filter=None, manager_id=None):
    return [u["username"] for u in get_all_users(role_filter, manager_id)]

def get_user_display_name(username):
    user_doc = db.collection(USERS_COLLECTION).document(username).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return f"{user_data.get('first_name', '')} {user_data.get('last_name', '')[:1]}."
    return username

def get_user_full_name(username):
    user_doc = db.collection(USERS_COLLECTION).document(username).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        return f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}"
    return username

def get_user_tasks(username=None):
    tasks_ref = db.collection(TASKS_COLLECTION)
    if username:
        tasks = tasks_ref.where("assigned_to", "==", username).stream()
    else:
        tasks = tasks_ref.stream()
    return [t.to_dict() for t in tasks]

def update_task_status(task_id, status):
    db.collection(TASKS_COLLECTION).document(task_id).update({"status": status})

def assign_task(title, description, assigned_to, assigned_by, due_datetime):
    task_ref = db.collection(TASKS_COLLECTION).document()
    task_ref.set({
        "id": task_ref.id,
        "title": title,
        "description": description,
        "assigned_to": assigned_to,
        "assigned_by": assigned_by,
        "status": "not started",
        "due_datetime": due_datetime.isoformat()
    })

def update_user_role(username, new_role, new_manager_id=""):
    db.collection(USERS_COLLECTION).document(username).update({"role": new_role, "manager_id": new_manager_id})

# === STREAMLIT FRONTEND SESSION ===
st.set_page_config(page_title="Task Manager")
if "user" not in st.session_state:
    st.session_state.user = None

st.title("Task Manager Login")
# === LOGIN / REGISTER ===
if st.session_state.user is None:
    choice = st.selectbox("Action", ["Login", "Register"])
    username = st.text_input("Username", key="login_username")
    password = st.text_input("Password", type="password", key="login_password")

    if choice == "Register":
        first_name = st.text_input("First Name", key="register_first")
        last_name = st.text_input("Last Name", key="register_last")

    if st.button("Submit", key="submit_auth"):
        if choice == "Login":
            user_data = login(username, password)
            if user_data:
                st.session_state.user = user_data
                st.rerun()
            else:
                st.error("Incorrect login")
        elif choice == "Register":
            if register_user(username, password, first_name, last_name):
                st.success("User registered, please log in.")
                st.rerun()
            else:
                st.error("Username already exists")

else:
    user = st.session_state.user
    st.write(f"Logged in as: {user['first_name']} {user['last_name']} ({user['role']})")
    if st.button("Logout", key="logout_button"):
        st.session_state.clear()
        st.rerun()

    # NAVIGATION
    nav_pages = ["Your Tasks"]
    if user["role"] in ["manager", "founder"]:
        nav_pages.extend(["Assign a Task", "All Tasks"])
    if user["role"] == "founder":
        nav_pages.append("User Management")

    page = st.selectbox("Navigate", nav_pages, key="page_select")
    if page == "Your Tasks":
        user_tasks = sorted(get_user_tasks(user["username"]), key=lambda x: x.get("due_datetime", ""))
        for task in user_tasks:
            due_dt = datetime.fromisoformat(task.get("due_datetime")) if task.get("due_datetime") else None
            overdue = due_dt and due_dt < datetime.now()
            overdue_label = "⚠️ Overdue" if overdue and task.get("status") != "complete" else ""
            st.write(f"{task['title']}: {task['description']} (Due: {task.get('due_datetime', 'N/A')}) {overdue_label}")
            status = st.selectbox("Update status", ["not started", "in progress", "complete"],
                                  index=["not started", "in progress", "complete"].index(task.get("status", "not started")),
                                  key=task["id"])
            if st.button("Update", key=f"update_{task['id']}"):
                update_task_status(task["id"], status)
                st.rerun()

    elif page == "Assign a Task":
        st.subheader("Assign a New Task")
        st.divider()
        with st.form("assign_task_form", clear_on_submit=True):
            available_users = get_all_users() if user["role"] == "founder" else get_all_users(role_filter="employee", manager_id=user["username"])
            display_names = [f"{u['first_name']} {u['last_name'][0]}." for u in available_users]
            username_map = {f"{u['first_name']} {u['last_name'][0]}." : u["username"] for u in available_users}


            assigned_display = st.selectbox("Assign to", display_names)
            assigned_to = username_map.get(assigned_display)

            title = st.text_input("Task Title")
            description = st.text_area("Task Description")
            due_date = st.date_input("Due Date")

            time_options = [f"{h}:{m:02d} {p}" for h in range(1, 13) for m in [0, 30] for p in ["AM", "PM"]]
            selected_time = st.selectbox("Due Time", time_options)

            submit = st.form_submit_button("Assign Task")
            if submit:
                hour_minute, period = selected_time.split(" ")
                hour, minute = map(int, hour_minute.split(":"))
                if period == "PM" and hour != 12:
                    hour += 12
                elif period == "AM" and hour == 12:
                    hour = 0
                due_datetime = datetime.combine(due_date, time(hour=hour, minute=minute))
                assign_task(title, description, assigned_to, user["username"], due_datetime)
                st.success("Task Assigned")

  # Clears form & reloads page
    elif page == "All Tasks":
        usernames = get_all_usernames() if user["role"] == "founder" else get_all_usernames(manager_id=user["username"])
        for username in usernames:
            st.subheader(f"{get_user_full_name(username)}")
            tasks = sorted(get_user_tasks(username), key=lambda x: x.get("due_datetime", ""))
            for task in tasks:
                due_dt = datetime.fromisoformat(task.get("due_datetime")) if task.get("due_datetime") else None
                overdue = due_dt and due_dt < datetime.now()
                overdue_label = "⚠️ Overdue" if overdue and task.get("status") != "complete" else ""
                st.write(f"{'✅' if task.get('status') == 'complete' else '⬜️'} {task['title']} (Status: {task.get('status')}, Due: {task.get('due_datetime', 'N/A')}, Assigned by: {get_user_full_name(task['assigned_by'])}) {overdue_label}")

    elif page == "User Management":
        st.subheader("Create User")
        new_username = st.text_input("New Username", key="create_user")
        new_password = st.text_input("New Password", type="password", key="create_pass")
        first_name = st.text_input("First Name", key="create_first")
        last_name = st.text_input("Last Name", key="create_last")
        new_role = st.selectbox("Role", ["employee", "manager", "founder"], key="create_role")

        manager_users = get_all_users(role_filter="manager")
        display_names = [f"{u['first_name']} {u['last_name'][0]}." for u in manager_users]
        manager_map = {f"{u['first_name']} {u['last_name'][0]}.": u["username"] for u in manager_users}

        manager_display = st.selectbox("New Manager Username (optional)", ["None"] + display_names, disabled=new_role == "founder", key="create_manager")
        manager_id = "" if manager_display == "None" or new_role == "founder" else manager_map.get(manager_display)

        if st.button("Create User", key="create_btn"):
            if register_user(new_username, new_password, first_name, last_name, new_role, manager_id):
                st.success("User created")
                st.rerun()
            else:
                st.error("Username already exists")

        st.divider()
        st.subheader("Update User Role")
        all_users = get_all_users()
        user_display_map = {f"{u['first_name']} {u['last_name'][0]}.": u["username"] for u in all_users}
        selected_display = st.selectbox("Select User to Update", list(user_display_map.keys()), key="update_user")
        selected_username = user_display_map[selected_display]

        updated_role = st.selectbox("New Role", ["employee", "manager", "founder"], key="update_role")

        manager_display = st.selectbox("New Manager Username (optional)", ["None"] + display_names, disabled=updated_role == "founder", key="update_manager")
        updated_manager_id = "" if manager_display == "None" or updated_role == "founder" else manager_map.get(manager_display)

        if st.button("Update Role", key="update_btn"):
            update_user_role(selected_username, updated_role, updated_manager_id)
            st.success("Role updated")
            st.rerun()
