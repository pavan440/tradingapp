import sqlite3
import hashlib
import os
import streamlit as st
import datetime
import pandas as pd
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv(override=True)

DB_PATH = os.path.join(os.path.expanduser("~"), ".tradingagents", "users.db")
ADMIN_EMAIL = "pavanpt05@gmail.com"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            email TEXT,
            password_hash TEXT,
            salt TEXT,
            is_admin BOOLEAN,
            is_approved BOOLEAN,
            last_login TEXT,
            created_at TEXT
        )
    ''')
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def send_admin_notification(new_username, new_email, is_super_user=False):
    gmail_user = None
    gmail_password = None
    
    # Check Streamlit secrets first
    try:
        if hasattr(st, "secrets"):
            gmail_user = st.secrets.get("GMAIL_USER")
            gmail_password = st.secrets.get("GMAIL_APP_PASSWORD")
    except Exception:
        pass
        
    # Fallback to .env / os.environ
    if not gmail_user:
        gmail_user = os.environ.get("GMAIL_USER")
    if not gmail_password:
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password:
        return False, "Skipped sending email: GMAIL_USER and GMAIL_APP_PASSWORD not found in st.secrets or .env"
        
    try:
        msg = EmailMessage()
        if is_super_user:
            msg.set_content(f"Hello,\n\nThe Super User account has been successfully created!\n\nSuper User ID: {new_username}\nEmail: {new_email}\n\nYou can now log in and manage your app.")
            msg['Subject'] = f"Super User Created - TradingAgents"
        else:
            msg.set_content(f"Hello Admin,\n\nA new user has requested access to TradingAgents.\n\nUsername: {new_username}\nEmail: {new_email}\n\nPlease log in to your Admin Panel to approve or deny this request.")
            msg['Subject'] = f"New Access Request from {new_username}"
            
        msg['From'] = gmail_user
        msg['To'] = ADMIN_EMAIL
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Failed to send email notification: {e}"

def send_user_status_notification(user_email, username, status="welcome"):
    gmail_user = None
    gmail_password = None
    
    try:
        if hasattr(st, "secrets"):
            gmail_user = st.secrets.get("GMAIL_USER")
            gmail_password = st.secrets.get("GMAIL_APP_PASSWORD")
    except Exception:
        pass
        
    if not gmail_user:
        gmail_user = os.environ.get("GMAIL_USER")
    if not gmail_password:
        gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_password or not user_email:
        return
        
    try:
        msg = EmailMessage()
        if status == "welcome":
            msg.set_content(f"Hello {username},\n\nWe have received your request to join TradingAgents!\n\nYour account is currently pending approval from the administrator. We will notify you again once you have been approved.\n\nThank you!")
            msg['Subject'] = "Welcome to TradingAgents - Approval Pending"
        elif status == "approved":
            msg.set_content(f"Hello {username},\n\nGreat news! Your account has been approved by the administrator.\n\nYou can now log in to TradingAgents and access the dashboard.\n\nEnjoy!")
            msg['Subject'] = "Your TradingAgents Account is Approved!"
            
        msg['From'] = gmail_user
        msg['To'] = user_email
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        pass

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()

def create_user(username, email, password, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username=?", (username,))
    if c.fetchone():
        conn.close()
        return False, "Username already exists.", ""
    
    salt = os.urandom(16).hex()
    pwd_hash = hash_password(password, salt)
    now = datetime.datetime.now().isoformat()
    
    # Super users are automatically approved
    is_approved = is_admin
    
    c.execute("INSERT INTO users (username, email, password_hash, salt, is_admin, is_approved, last_login, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
              (username, email, pwd_hash, salt, is_admin, is_approved, None, now))
    conn.commit()
    conn.close()
    
    email_success, email_msg = send_admin_notification(username, email, is_super_user=is_admin)
    
    if not is_admin:
        # Also notify the user that their request was received
        send_user_status_notification(email, username, status="welcome")
    
    if is_admin:
        return True, "Super User successfully created!", email_msg
    else:
        return True, "Sign up successful! Please wait for an admin to approve your account.", email_msg

def check_login(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash, salt, is_admin, is_approved FROM users WHERE username=?", (username,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return False, "Invalid username or password.", False
        
    pwd_hash, salt, is_admin, is_approved = row
    
    if hash_password(password, salt) == pwd_hash:
        if not is_approved:
            conn.close()
            return False, "Your account is pending admin approval.", False
            
        now = datetime.datetime.now().isoformat()
        c.execute("UPDATE users SET last_login=? WHERE username=?", (now, username))
        conn.commit()
        conn.close()
        return True, "Success", is_admin
        
    conn.close()
    return False, "Invalid username or password.", False

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT username, email, is_admin, is_approved, last_login, created_at FROM users", conn)
    conn.close()
    return df

def toggle_approval(username, current_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_approved=? WHERE username=?", (not current_status, username))
    
    # If they are being approved (False -> True), send them an email
    if not current_status:
        c.execute("SELECT email FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if row and row[0]:
            send_user_status_notification(row[0], username, status="approved")
            
    conn.commit()
    conn.close()

def auth_ui():
    init_db()
    
    # ---------------------------------------------------------
    # HIDDEN SUPER USER CREATION ROUTE
    # Access via URL: http://localhost:8501/?setup=admin
    # ---------------------------------------------------------
    if st.query_params.get("setup") == "admin":
        st.title("👑 Super User Setup")
        st.info("This is the hidden admin setup page. Create your master account here.")
        
        with st.form("superuser_form"):
            admin_id = st.text_input("Choose Super User ID")
            admin_email = st.text_input("Admin Email Address", value=ADMIN_EMAIL)
            admin_password = st.text_input("Choose Admin Password", type="password")
            confirm_admin_password = st.text_input("Confirm Admin Password", type="password")
            submit_super = st.form_submit_button("Create Super User")
            
            if submit_super:
                if not admin_id or not admin_password:
                    st.error("Please fill in all fields.")
                elif admin_password != confirm_admin_password:
                    st.error("Passwords do not match.")
                else:
                    success, msg, email_msg = create_user(admin_id, admin_email, admin_password, is_admin=True)
                    if success:
                        st.success(msg)
                        if "sent successfully" in email_msg:
                            st.info("An email confirmation has been sent.")
                        else:
                            st.warning(f"Email Note: {email_msg}")
                        st.balloons()
                        st.info("You can now remove '?setup=admin' from the URL and log in normally!")
                    else:
                        st.error(msg)
        return False # Stop here, don't load the rest of the app
    # ---------------------------------------------------------

    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if st.session_state.authenticated:
        if st.session_state.get('is_admin'):
            with st.sidebar:
                st.markdown("---")
                st.markdown("### 👑 Super User Panel")
                if st.button("Manage Users"):
                    st.session_state.show_admin = not st.session_state.get('show_admin', False)
                
                if st.button("Logout"):
                    st.session_state.authenticated = False
                    st.session_state.is_admin = False
                    st.rerun()
                    
            if st.session_state.get('show_admin', False):
                st.title("🛡️ Super User Dashboard")
                
                users_df = get_all_users()
                
                # --- APP STATISTICS ---
                total_users = len(users_df)
                approved_users = len(users_df[users_df['is_approved'] == True])
                pending_users = len(users_df[users_df['is_approved'] == False])
                admins = len(users_df[users_df['is_admin'] == True])
                
                col_a, col_b, col_c, col_d = st.columns(4)
                col_a.metric("Total Accounts", total_users)
                col_b.metric("Approved Users", approved_users)
                col_c.metric("Pending Approval", pending_users)
                col_d.metric("Super Users", admins)
                
                st.markdown("---")
                st.subheader("Manage User Access")
                
                users_df = users_df.sort_values(by=['is_approved', 'created_at'], ascending=[True, False])
                
                for index, row in users_df.iterrows():
                    with st.container():
                        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                        col1.write(f"**{row['username']}** {'👑' if row['is_admin'] else ''}\n\n*{row['email']}*")
                        
                        status = "✅ Approved" if row['is_approved'] else "⏳ Pending"
                        col2.write(status)
                        
                        last_login = row['last_login'][:19].replace('T', ' ') if row['last_login'] else 'Never'
                        col3.write(f"Last Login:\n{last_login}")
                        
                        if not row['is_admin']: # Prevent deleting other admins or self
                            btn_text = "Revoke Access" if row['is_approved'] else "Approve User"
                            if col4.button(btn_text, key=f"btn_{row['username']}"):
                                toggle_approval(row['username'], row['is_approved'])
                                st.rerun()
                    st.markdown("---")
                
                if st.button("Back to App", type="primary"):
                    st.session_state.show_admin = False
                    st.rerun()
                return False
        else:
            with st.sidebar:
                st.markdown("---")
                st.markdown(f"👤 **{st.session_state.username}**")
                if st.button("Logout"):
                    st.session_state.authenticated = False
                    st.rerun()
                    
        return True
        
    else:
        st.title("Welcome to TradingAgents")
        st.write("Please log in or request access to continue.")
        
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            with st.form("login_form"):
                username = st.text_input("Username").strip()
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Login")
                
                if submit:
                    if username and password:
                        success, msg, is_admin = check_login(username, password)
                        if success:
                            st.session_state.authenticated = True
                            st.session_state.username = username
                            st.session_state.is_admin = is_admin
                            st.rerun()
                        else:
                            if "pending" in msg.lower():
                                st.warning(msg)
                            else:
                                st.error(msg)
        
        with tab2:
            with st.form("signup_form"):
                new_username = st.text_input("Choose a Username (ID)").strip()
                new_email = st.text_input("Email Address").strip()
                new_password = st.text_input("Choose a Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                submit_signup = st.form_submit_button("Request Access")
                
                if submit_signup:
                    if not new_username or not new_email or not new_password:
                        st.error("Please fill in all fields.")
                    elif "@" not in new_email:
                        st.error("Please enter a valid email address.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters long.")
                    else:
                        success, msg, email_msg = create_user(new_username, new_email, new_password, is_admin=False)
                        if success:
                            st.success(msg)
                            if "sent successfully" in email_msg:
                                st.info("The super user has been notified by email. You will be able to log in with your Username and Password once approved.")
                            else:
                                st.warning(f"Note: Your account was created, but email notification failed ({email_msg}). The Super User will see your request in their dashboard.")
                        else:
                            st.error(msg)
                            
        return False
