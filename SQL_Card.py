import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re

# Step 1: Nhập link từ user
folder_url = st.text_input("Dán link thư mục Google Drive (công khai):")

# Step 2: Tạo credentials từ secrets
creds_dict = dict(st.secrets["gcp_service_account"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)

# Step 3: Hàm extract folder ID
def extract_folder_id(url):
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None

# Step 4: Nếu có link, tiến hành lấy dữ liệu
if folder_url:
    folder_id = extract_folder_id(folder_url)
    if folder_id:
        try:
            # Kết nối Google Drive API
            drive_service = build('drive', 'v3', credentials=credentials)

            # Gọi API: lấy danh sách file trong folder
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id, name, mimeType, webViewLink)"
            ).execute()

            files = results.get('files', [])

            # Hiển thị kết quả
            if files:
                st.success(f"Đã tìm thấy {len(files)} file:")
                for file in files:
                    st.markdown(f"- [{file['name']}]({file['webViewLink']}) ({file['mimeType']})")
            else:
                st.info("Không có file nào trong thư mục.")
        except Exception as e:
            st.error(f"Lỗi khi truy cập thư mục: {e}")
    else:
        st.warning("Không thể lấy folder ID từ đường dẫn.")

import sqlite3
import os
from io import BytesIO
from googleapiclient.http import MediaIoBaseUpload

# Giả sử bạn đã có folder_id từ đoạn code trước

def create_local_db_with_quotes(db_path):
    conn = sqlite3.connect(db_path)
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

# Hàm upload file lên Drive folder
def upload_file_to_drive(service, file_path, folder_id):
    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(open(file_path, 'rb'), mimetype='application/x-sqlite3')
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
    return uploaded_file

# Giao diện Streamlit bổ sung
db_name = st.text_input("Nhập tên file .db muốn tạo (ví dụ: quotes.db):")

if st.button("Tạo file .db và upload lên Drive"):
    if not folder_url:
        st.warning("Vui lòng nhập link thư mục Google Drive trước.")
    elif not db_name:
        st.warning("Vui lòng nhập tên file .db.")
    else:
        folder_id = extract_folder_id(folder_url)
        if not folder_id:
            st.error("Không lấy được folder ID từ URL.")
        else:
            local_db_path = db_name  # tạo file local tạm thời
            try:
                create_local_db_with_quotes(local_db_path)

                # Kết nối Drive API (giữ nguyên credentials, drive_service)
                uploaded_file = upload_file_to_drive(drive_service, local_db_path, folder_id)
                st.success(f"File '{uploaded_file['name']}' đã được tạo và upload lên Drive thành công (ID: {uploaded_file['id']})")

                # Xóa file local tạm nếu muốn
                os.remove(local_db_path)

            except Exception as e:
                st.error(f"Lỗi khi tạo hoặc upload file: {e}")
