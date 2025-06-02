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
