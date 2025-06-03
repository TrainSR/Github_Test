import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.http import MediaIoBaseDownload
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

# --- Hàm cập nhật và tải lên Drive ---
def update_db_and_upload(file_id, df):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        conn = sqlite3.connect(tmp.name)
        df.to_sql("quotes", conn, if_exists="replace", index=False)
        conn.close()

        tmp.seek(0)
        media = MediaIoBaseUpload(open(tmp.name, "rb"), mimetype='application/x-sqlite3')
        updated_file = drive_service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
    return updated_file

def create_empty_db_file(folder_id, filename="new_database.db"):
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


def download_db_file(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh

def load_quotes_from_drive(file_id):
    content = download_db_file(file_id)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(content.read())
        tmp.flush()
        conn = sqlite3.connect(tmp.name)
        df = pd.read_sql_query("SELECT * FROM quotes", conn)
        conn.close()
    return df

def get_all_quotes():
    return st.session_state.get("quotes_df", pd.DataFrame())

def get_random_quote():
    df = get_all_quotes()
    if df.empty:
        return None
    return df.sample(1).iloc[0]

# === Giao diện chính ===

def main_ui():
    st.title("📚 Quote Database Manager")

    tab4, tab1, tab2, tab3 = st.tabs([
        "🎲 Random Quote",
        "➕ Thêm Quote", 
        "✏️ Sửa Quote", 
        "🗑️ Xóa Quote"
    ])

    with tab4:
        st.subheader("🎲")

        if "random_quote" not in st.session_state:
            st.session_state.random_quote = get_random_quote()

        quote = st.session_state.random_quote

        if quote is None:
            st.info("Chưa có quote nào trong database.")
        else:
            dau = f"({quote['date']})" if quote['date'] else ""
            content_md = quote['content'].replace('\n', '<br>')

            st.markdown(f"""
            <div style='font-size: 22px; line-height: 1.6; font-weight: bold;'>
            {content_md}
            </div>
            <div style='font-size: 18px; margin-top: 10px;'>
            - <i>{quote['speaker']} {quote['note']}</i> {dau}<br><br>
            🏷️ <code>{quote['tag']}</code>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🎲 Quote khác"):
            st.session_state.random_quote = get_random_quote()
    with tab1:
        st.subheader("➕ Thêm quote mới")

        with st.form("add_quote_form"):
            content = st.text_area("📜 Nội dung", height=150)
            speaker = st.text_input("👤 Người nói")
            note = st.text_input("📝 Ghi chú (tuỳ chọn)")
            date = st.text_input("📅 Ngày (tuỳ chọn)")
            tag = st.text_input("🏷️ Tag")

            submitted = st.form_submit_button("✅ Thêm quote")
            if submitted:
                if not content.strip():
                    st.warning("⚠️ Nội dung không được để trống.")
                else:
                    # Thay " thành ' trong nội dung
                    cleaned_content = f'"{content.replace('"', "'").strip()}"'

                    # Tính ID mới
                    df = st.session_state["quotes_df"]
                    new_id = int(df["id"].max() + 1) if not df.empty else 1
                    new_row = {
                        "id": new_id,
                        "content": cleaned_content,
                        "speaker": speaker.strip(),
                        "note": note.strip(),
                        "date": date.strip(),
                        "tag": tag.strip()
                    }
                    st.session_state["quotes_df"] = pd.concat(
                        [st.session_state["quotes_df"], pd.DataFrame([new_row])],
                        ignore_index=True
                    )
                    st.success("✅ Đã thêm quote mới vào bộ nhớ tạm.")
    with tab2:
        st.subheader("📋 Danh sách toàn bộ quote")

        df = get_all_quotes()
        if df.empty:
            st.info("Chưa có quote nào.")
        else:
            # Hiển thị toàn bộ bảng
            st.dataframe(df, use_container_width=True)

            st.markdown("### 🔍 Tìm và sửa quote")
            search_text = st.text_input("Tìm quote theo nội dung hoặc tag:")
            filtered_df = df[
                df["content"].str.contains(search_text, case=False, na=False) |
                df["tag"].str.contains(search_text, case=False, na=False)
            ]

            if not filtered_df.empty:
                quote_options = {
                    f"{row['id']} | {row['content'][:50]}...": row['id']
                    for _, row in filtered_df.iterrows()
                }
                selected_label = st.selectbox("Chọn quote để sửa:", list(quote_options.keys()))
                selected_id = quote_options[selected_label]
                selected_row = df[df["id"] == selected_id].iloc[0]

                st.markdown("---")
                st.markdown(f"### ✏️ Sửa Quote ID {selected_id}")

                with st.form("edit_selected_quote"):
                    new_content = st.text_area("📝 Nội dung", selected_row["content"])
                    new_speaker = st.text_input("🗣️ Người nói", selected_row["speaker"])
                    new_note = st.text_input("📌 Ghi chú", selected_row["note"])
                    new_date = st.text_input("📅 Ngày", selected_row["date"])
                    new_tag = st.text_input("🏷️ Tag", selected_row["tag"])

                    submit_edit = st.form_submit_button("💾 Lưu thay đổi")

                    if submit_edit:
                        idx = df[df["id"] == selected_id].index[0]
                        st.session_state["quotes_df"].at[idx, "content"] = new_content
                        st.session_state["quotes_df"].at[idx, "speaker"] = new_speaker
                        st.session_state["quotes_df"].at[idx, "note"] = new_note
                        st.session_state["quotes_df"].at[idx, "date"] = new_date
                        st.session_state["quotes_df"].at[idx, "tag"] = new_tag
                        st.success("✅ Đã cập nhật quote.")
            else:
                st.info("Không tìm thấy quote nào khớp.")
    with tab3:
        st.subheader("🗑️ Xóa nhiều quote")

        df = get_all_quotes()
        if df.empty:
            st.info("Chưa có quote nào để xóa.")
        else:
            search_text = st.text_input("🔍 Tìm quote theo nội dung hoặc tag để lọc:")
            filtered_df = df[
                df["content"].str.contains(search_text, case=False, na=False) |
                df["tag"].str.contains(search_text, case=False, na=False)
            ] if search_text else df

            if not filtered_df.empty:
                filtered_df["label"] = filtered_df.apply(
                    lambda row: f"{row['id']} | {row['content'][:50]}...", axis=1
                )
                selected_labels = st.multiselect(
                    "Chọn các quote để xóa:", 
                    options=filtered_df["label"].tolist()
                )
                
                selected_ids = [
                    int(label.split("|")[0].strip()) for label in selected_labels
                ]

                if selected_ids:
                    st.warning(f"Bạn sắp xóa {len(selected_ids)} quote.")
                    if st.button("❌ Xác nhận xóa"):
                        st.session_state["quotes_df"] = df[~df["id"].isin(selected_ids)].reset_index(drop=True)
                        st.success(f"✅ Đã xóa {len(selected_ids)} quote.")
            else:
                st.info("Không tìm thấy quote nào khớp.")




# === Sidebar chọn DB ===

st.sidebar.title("⚙️ Cài đặt Database")
folder_url = st.sidebar.text_input("📂 Nhập link thư mục Google Drive chứa DB:")
folder_id = extract_folder_id(folder_url) if folder_url else None
selected_db_file = None

if st.sidebar.button("➕ Tạo file database rỗng"):
    if folder_id:
        new_file = create_empty_db_file(folder_id)
        st.sidebar.success(f"Đã tạo file: `{new_file['name']}` (ID: {new_file['id']})")
    else:
        st.sidebar.warning("Vui lòng nhập link thư mục trước.")

if folder_id:
    try:
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

if selected_db_file:
    if (
        "quotes_df" not in st.session_state
        or st.session_state.get("selected_db_id") != selected_db_file["id"]
    ):
        st.session_state["selected_db_id"] = selected_db_file["id"]
        quotes_df = load_quotes_from_drive(selected_db_file["id"])
        st.session_state["quotes_df"] = quotes_df
        st.sidebar.success(f"Đã nạp {len(quotes_df)} quote từ `{selected_db_file['name']}`.")
    else:
        quotes_df = st.session_state["quotes_df"]
    main_ui()
    # --- Trong phần sidebar sau khi chọn selected_db_file ---
    if selected_db_file:
        if st.sidebar.button("💾 Cập nhật & Tải lên Drive"):
            df_to_save = st.session_state.get("quotes_df")
            if df_to_save is not None and not df_to_save.empty:
                try:
                    update_db_and_upload(selected_db_file["id"], df_to_save)
                    st.sidebar.success("✅ Đã cập nhật database và tải lên Drive thành công.")
                except Exception as e:
                    st.sidebar.error(f"❌ Lỗi khi tải lên Drive: {e}")
            else:
                st.sidebar.warning("⚠️ Database trống, không có gì để cập nhật.")
else:
    st.sidebar.info("🔑 Vui lòng nhập link thư mục Google Drive hợp lệ.")
