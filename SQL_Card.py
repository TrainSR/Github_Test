import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.http import MediaIoBaseDownload
import io
import sqlite3
import tempfile
import pandas as pd
import re
import random

# Lấy thông tin credentials từ secrets
creds_dict = dict(st.secrets["gcp_service_account"])
credentials = service_account.Credentials.from_service_account_info(creds_dict)
drive_service = build('drive', 'v3', credentials=credentials)


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

def extract_folder_id(url):
    if "folders/" in url:
        return url.split("folders/")[1].split("?")[0]
    elif "id=" in url:
        return url.split("id=")[1].split("&")[0]
    else:
        return None
def quote_edit_form(selected_row):
    df = st.session_state.get("quotes_df", pd.DataFrame())

    speaker_suggestions = sorted(df["speaker"].dropna().unique()) if not df.empty else []
    tag_suggestions = sorted(df["tag"].dropna().unique()) if not df.empty else []

    content = st.text_area("📝 Nội dung", selected_row["content"])

    col1, col2 = st.columns(2)
    with col1:
        speaker_manual = st.text_input("👤 Nhập người nói (mới)", value="")
    with col2:
        speaker_select = st.selectbox("📚 Chọn người nói (có sẵn)", options=[""] + speaker_suggestions, index=(
            speaker_suggestions.index(selected_row["speaker"]) + 1 if selected_row["speaker"] in speaker_suggestions else 0
        ))

    note = st.text_input("📌 Ghi chú", selected_row["note"])
    date = st.text_input("📅 Ngày", selected_row["date"])
    link = st.text_input("🔗 Link", selected_row["link"])

    current_tags = selected_row["tag"].split()

    all_tags = sorted(df["tag"].dropna().str.split().sum()) if not df.empty else []
    all_tags = sorted(set(all_tags))

    tags_selected = st.multiselect("🏷️ Chọn hoặc nhập nhiều tag", options=all_tags, default=current_tags)
    manual_tag_input = st.text_input("🏷️ Nhập thêm tag mới (cách nhau bởi dấu cách)", value="")

    all_final_tags = tags_selected + manual_tag_input.split()
    all_final_tags = list({t.strip() for t in all_final_tags if t.strip()})
    tag = " ".join(all_final_tags)

    speaker = speaker_manual.strip() if speaker_manual.strip() else speaker_select.strip()
    return content, speaker, note, date, tag, link

def truncate_at_special_chars(filename, extension=".db"):
    # Cắt tại ký tự không phải chữ cái, số, hoặc dấu gạch dưới
    match = re.search(r'[^a-zA-Z0-9_]', filename)
    if match:
        filename = filename[:match.start()]
    
    filename = filename.strip()

    # Nếu rỗng thì đặt tên mặc định
    if not filename:
        filename = "untitled"

    return filename + extension

def quote_input_form():
    df = st.session_state.get("quotes_df", pd.DataFrame())

    speaker_suggestions = sorted(df["speaker"].dropna().unique()) if not df.empty else []
    tag_suggestions = sorted(df["tag"].dropna().unique()) if not df.empty else []

    content = st.text_area("📜 Nội dung", height=150)

    # --- Speaker: 2 cột ---
    col1, col2 = st.columns(2)
    with col1:
        speaker_manual = st.text_input("👤 Nhập người nói (mới)")
    with col2:
        speaker_select = st.selectbox("📚 Chọn người nói (có sẵn)", options=[""] + speaker_suggestions)

    # --- Note, Date, Link ---
    note = st.text_input("📝 Ghi chú (tuỳ chọn)")
    date = st.text_input("📅 Ngày (tuỳ chọn)")
    link = st.text_input("🔗 Link (tuỳ chọn)")

    # --- Tag: 2 cột ---
    col3, col4 = st.columns(2)
    with col3:
        tag_manual_raw = st.text_input("🏷️ Nhập tag mới (phân tách bằng dấu cách)")
        tag_manual_list = [t.strip() for t in tag_manual_raw.split() if t.strip()]
    with col4:
        tag_select_list = st.multiselect("📚 Chọn tag có sẵn", options=tag_suggestions)

    # --- Merge speaker ---
    speaker = speaker_manual.strip() if speaker_manual.strip() else speaker_select.strip()

    # --- Merge tag ---
    tag_list = list(set(tag_manual_list + tag_select_list))
    tag = " ".join(tag_list) if tag_list else ""

    return content, speaker, note, date, tag, link


def delete_db_file(folder_id, filename):
    """Xoá file theo tên trong thư mục cụ thể"""
    try:
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and name = '{filename}'",
            fields="files(id, name)",
            pageSize=1
        ).execute()
        files = results.get("files", [])
        if files:
            file_id = files[0]["id"]
            drive_service.files().delete(fileId=file_id).execute()
            return True
        return False
    except Exception as e:
        print(f"Lỗi xoá file: {e}")
        return False

def create_empty_db_file(folder_id, filename):
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
                tag TEXT,
                link TEXT
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

def get_random_quote(df=None):
    if df is None:
        df = st.session_state.get("quotes_df")
    if df is None or df.empty:
        return None
    return df.sample(1).iloc[0].to_dict()
def update_reload():
    global selected_db_file
    df_to_save = st.session_state.get("quotes_df")
    if df_to_save is not None and not df_to_save.empty:
        try:
            update_db_and_upload(selected_db_file["id"], df_to_save)
            st.sidebar.success("✅ Đã cập nhật database và tải lên Drive thành công.")
        except Exception as e:
            st.sidebar.error(f"❌ Lỗi khi tải lên Drive: {e}")
    else:
        st.sidebar.warning("⚠️ Database trống, không có gì để cập nhật.")
# === Giao diện chính ===

def main_ui():
    with tab4:
        df = st.session_state.get("quotes_df")
        if df is None or df.empty:
            st.info("Chưa có quote nào trong database.")
        else:
            all_tags = sorted(set(tag for tags in df["tag"].dropna() for tag in tags.split(" ")))
            try:
                all_tags.remove("")
            except:
                pass

            with st.sidebar:
                st.markdown("🎛️ **Bộ lọc Tag Random**")

                included_tags = st.multiselect("✅ Bao gồm 1 trong các tag:", options=all_tags, key="include_tags")

                excluded_tags = st.multiselect(
                    "🚫 Loại bỏ các tag:",
                    options=all_tags,
                    default=all_tags,  # Mặc định loại bỏ toàn bộ tag
                    key="exclude_tags"
                )
            def quote_filter(row):
                tags = set(row["tag"].split()) if pd.notna(row["tag"]) else set()
                include_ok = not included_tags or any(tag in tags for tag in included_tags)
                exclude_ok = not any(tag in tags for tag in excluded_tags)
                return include_ok and exclude_ok

            filtered_df = df[df.apply(quote_filter, axis=1)]

            quote = None
            if not filtered_df.empty:
                quote = filtered_df.sample(1).iloc[0]
                dau = f"({quote['date']})" if quote['date'] else ""
                content_md = quote['content'].replace('\n', '<br>')
                st.markdown(f"""
                {quote['link']}
                <div style='font-size: 22px; line-height: 1.6; font-weight: bold;'>
                {content_md}
                </div>
                <div style='font-size: 18px; margin-top: 10px;'>
                - <i>{quote['speaker']} {quote['note']}</i> {dau}<br>
                🏷️ <code>{quote['tag']}</code><br>
                🆔 ID: {quote['id']}
                </div><br>
                """, unsafe_allow_html=True)
            else:
                st.warning("Không có quote nào phù hợp với bộ lọc.")

            col2, col1 = st.columns(2)

            with col1:
                if st.button("🎲 Quote khác"):
                    pass

            with col2:
                if st.button("📝 Pending"):
                    quote_id = quote["id"]
                    df.loc[df["id"] == quote_id, "tag"] = df.loc[df["id"] == quote_id, "tag"].apply(
                        lambda t: "#pending" if pd.isna(t) else t if "#pending" in t else f"{t} #pending"
                    )
                    st.session_state["quotes_df"] = df
                    st.success("✅ Đã gắn tag #pending cho quote này.")
    with tab1:
        st.subheader("➕ Thêm quote mới")

        with st.form("add_quote_form"):
            content, speaker, note, date, tag, link = quote_input_form()

            submitted = st.form_submit_button("✅ Thêm quote")
            if submitted:
                if not any([content, speaker, note, date, tag, link]):
                    st.warning("⚠️ Ít nhất phải có một trường được điền.")
                else:
                    cleaned_content = content.strip().strip('"').replace('"', "'")
                    df = st.session_state["quotes_df"]
                    new_id = int(df["id"].max() + 1) if not df.empty else 1
                    new_row = {
                        "id": new_id,
                        "content": f'"{cleaned_content}"',
                        "speaker": speaker.strip(),
                        "note": note.strip(),
                        "date": date.strip(),
                        "tag": tag.strip(),
                        "link": link.strip()
                    }
                    st.session_state["quotes_df"] = pd.concat(
                        [st.session_state["quotes_df"], pd.DataFrame([new_row])],
                        ignore_index=True
                    )
                    st.success("✅ Đã thêm quote mới vào bộ nhớ tạm.")
                    update_reload()

    with tab2:
        with st.expander("📋 Danh sách toàn bộ quote"):
            df = get_all_quotes()
            if df.empty:
                st.info("Chưa có quote nào.")
            else:
                df["normalized_content"] = df["content"].str.strip().str.lower()
                st.dataframe(df.drop(columns=["normalized_content"]), use_container_width=True)

                st.markdown("### 🔁 Các quote bị trùng nội dung")
                duplicates = df[df.duplicated("normalized_content", keep=False)].sort_values("normalized_content")
                if not duplicates.empty:
                    st.dataframe(duplicates.drop(columns=["normalized_content"]), use_container_width=True)
                else:
                    st.info("✅ Không có quote nào bị trùng.")

        st.markdown("### 🔍 Tìm và sửa quote")
        search_text = st.text_input("Tìm quote theo nội dung hoặc tag:")
        filtered_df = df[
            df["content"].str.contains(search_text, case=False, na=False) |
            df["tag"].str.contains(search_text, case=False, na=False)
        ]

        if not filtered_df.empty:
            # Tạo mapping label -> index (vị trí dòng trong df)
            quote_options = {
                f"{idx} | {row['content'][:50]}...": idx
                for idx, row in filtered_df.iterrows()
            }
            selected_label = st.selectbox("Chọn quote để sửa:", list(quote_options.keys()))
            selected_index = quote_options[selected_label]
            selected_row = df.iloc[selected_index]

            with st.expander(f"✏️ Sửa Quote tại index {selected_index}"):
                with st.form("edit_selected_quote"):
                    new_content, new_speaker, new_note, new_date, new_tag, new_link = quote_edit_form(selected_row)
                    submit_edit = st.form_submit_button("💾 Lưu thay đổi")

                    if submit_edit:
                        st.session_state["quotes_df"].at[selected_index, "content"] = new_content
                        st.session_state["quotes_df"].at[selected_index, "speaker"] = new_speaker
                        st.session_state["quotes_df"].at[selected_index, "note"] = new_note
                        st.session_state["quotes_df"].at[selected_index, "date"] = new_date
                        st.session_state["quotes_df"].at[selected_index, "tag"] = new_tag
                        st.session_state["quotes_df"].at[selected_index, "link"] = new_link
                        st.success("✅ Đã cập nhật quote.")
                        update_reload()
        else:
            st.info("Không tìm thấy quote nào khớp.")

    with tab3:
        st.markdown("### 🎯 Chọn database mục tiêu để Copy/Move")
        target_db_name = st.selectbox(
            "🗃️ Chọn database khác để sao chép/di chuyển (ngoại trừ file hiện tại):",
            [f["name"] for f in db_files if f["id"] != selected_db_file["id"]]
        )
        target_db_file = next((f for f in db_files if f["name"] == target_db_name), None)
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
                # Dùng index của filtered_df làm key chọn
                options = [f"{idx} | {row['content'][:50]}..." for idx, row in filtered_df.iterrows()]

                select_all = st.checkbox("✅ Chọn tất cả")

                selected = st.multiselect(
                    "Chọn quote để xóa:",
                    options,
                    default=options if select_all else []
                )

                # Lấy index thay vì id
                selected_ids = [int(s.split("|")[0].strip()) for s in selected]



                if selected_ids:
                    st.warning(f"🔔 Bạn đã chọn {len(selected_ids)} quote.")

                    col_copy, col_move, col_delete = st.columns(3)
                # selected_ids là list index (int)
                
                    if col_copy.button("📄 Copy sang database khác"):
                        if target_db_file:
                            target_df = load_quotes_from_drive(target_db_file["id"])
                            # Lấy rows theo index
                            rows_to_copy = df.iloc[selected_ids].copy()
                            rows_to_copy["id"] = target_df["id"].max() + 1 if not target_df.empty else 1
                            target_df = pd.concat([target_df, rows_to_copy], ignore_index=True)
                            update_db_and_upload(target_db_file["id"], target_df)
                            st.success(f"✅ Đã copy {len(rows_to_copy)} quote sang `{target_db_file['name']}`.")

                    if col_delete.button("❌ Xác nhận xóa"):
                        st.session_state["quotes_df"] = df.drop(index=selected_ids).reset_index(drop=True)
                        st.success(f"✅ Đã xóa {len(selected_ids)} quote.")
                        update_reload()

            else:
                st.info("Không tìm thấy quote nào khớp.")

# === Sidebar chọn DB ===

st.sidebar.title("⚙️ Cài đặt Database")
folder_url = st.sidebar.text_input("📂 Nhập link thư mục Google Drive chứa DB:")
folder_id = extract_folder_id(folder_url) if folder_url else None
selected_db_file = None
new_file_name = truncate_at_special_chars(st.sidebar.text_input("Nhập tên file database cần tạo hoặc xóa"))


if st.sidebar.button("➕ Tạo file database rỗng"):
    if folder_id:
        new_file = create_empty_db_file(folder_id, new_file_name)
        st.sidebar.success(f"Đã tạo file: `{new_file['name']}` (ID: {new_file['id']})")
    else:
        st.sidebar.warning("Vui lòng nhập link thư mục trước.")

if st.sidebar.button("🗑️ Xoá file database"):
    if folder_id:
        success = delete_db_file(folder_id, new_file_name)
        if success:
            st.sidebar.success(f"✅ Đã xoá file: `{new_file_name}`")
        else:
            st.sidebar.error(f"❌ Không tìm thấy hoặc không thể xoá: `{new_file_name}`")
    else:
        st.sidebar.warning("⚠️ Vui lòng nhập link thư mục trước.")


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
df = st.session_state.get("quotes_df")
st.title("📚 Quote Database Manager")

tab4, tab1, tab2, tab3 = st.tabs([
    "🎲 Random Quote",
    "➕ Thêm Quote", 
    "✏️ Sửa Quote", 
    "🗑️ Xóa Quote"
])

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
else:
    st.sidebar.info("🔑 Vui lòng nhập link thư mục Google Drive hợp lệ.")
if "quotes_df" in st.session_state:
    if st.sidebar.button("🧮 Gán lại ID theo dòng (0-based index)"):
        df = st.session_state["quotes_df"]
        df["id"] = df.index
        st.session_state["quotes_df"] = df
        st.sidebar.success("✅ Đã cập nhật cột `id` thành index dòng.")
        update_reload()
