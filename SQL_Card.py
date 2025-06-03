import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import sqlite3
import tempfile
import pandas as pd
import random
import os

# Lấy thông tin credentials từ secrets
creds_dict = dict(st.secrets["gcp_service_account"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
drive_service = build('drive', 'v3', credentials=credentials)

# Hàm lấy folder ID từ URL
def extract_folder_id(url):
    if "folders/" in url:
        return url.split("folders/")[1].split("?")[0]
    elif "id=" in url:
        return url.split("id=")[1].split("&")[0]
    else:
        return None

# Hàm tạo file db rỗng
import sqlite3
import tempfile
from googleapiclient.http import MediaIoBaseUpload

def create_empty_db_file(folder_id, filename="new_database.db"):
    # Tạo file SQLite tạm thời và tạo bảng
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                speaker TEXT,
                note TEXT,
                date TEXT,
                tag TEXT
            )
        ''')

        conn.commit()
        conn.close()

        tmp.seek(0)
        media = MediaIoBaseUpload(tmp, mimetype='application/octet-stream')

        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'application/x-sqlite3'
        }

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()

        return file

# Giao diện streamlit
st.title("Truy cập Google Drive Folder")

folder_url = st.text_input("Dán link thư mục Google Drive:")
folder_id = extract_folder_id(folder_url) if folder_url else None

if folder_id:
    # Hiển thị file hiện tại trong folder
    st.subheader("Danh sách file:")
    results = drive_service.files().list(q=f"'{folder_id}' in parents",
                                         pageSize=100,
                                         fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    for file in files:
        st.write(f"📄 {file['name']}")

    # Nút tạo file db rỗng
    if st.button("➕ Tạo file database rỗng"):
        new_file = create_empty_db_file(folder_id)
        st.success(f"Đã tạo file: `{new_file['name']}` (ID: {new_file['id']})")
else:
    st.info("Vui lòng nhập link thư mục Google Drive hợp lệ.")








# --- Sidebar chọn DB từ Drive ---
st.sidebar.title("⚙️ Cài đặt Database")

folder_url = st.sidebar.text_input("📂 Nhập link thư mục Google Drive chứa DB:")
folder_id = extract_folder_id(folder_url) if folder_url else None

selected_db_file = None

if folder_id:
    try:
        # Lấy danh sách file .db trong folder
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and name contains '.db'",
            fields="files(id, name)",
            pageSize=100
        ).execute()

        db_files = results.get("files", [])

        if db_files:
            file_names = [f["name"] for f in db_files]
            selected_name = st.sidebar.selectbox("🗃️ Chọn database:", file_names)
            selected_db_file = next(f for f in db_files if f["name"] == selected_name)
        else:
            st.sidebar.warning("❗ Không tìm thấy file .db trong thư mục.")
    except Exception as e:
        st.sidebar.error(f"Lỗi khi truy cập Drive: {e}")
else:
    st.sidebar.info("🔑 Vui lòng nhập link thư mục Google Drive hợp lệ.")

# Hiển thị file đã chọn
if selected_db_file:
    st.sidebar.success(f"Đã chọn: `{selected_db_file['name']}`")
    st.session_state["selected_db_id"] = selected_db_file["id"]  # Lưu ID để dùng sau
