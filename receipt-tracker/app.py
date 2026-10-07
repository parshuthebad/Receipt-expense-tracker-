import json
import smtplib
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

from billing import (
    bill_context,
    build_summary,
    clean_df,
    compute_split,
    empty_df,
    money,
    parse_names,
)
from prompts import EXTRACT_PROMPT, SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE

MODEL_NAME = st.secrets.get("GEMINI_MODEL", "gemini-3.5-flash")

st.set_page_config(page_title="ReceiptBuddy", page_icon="🧾")

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GMAIL_ADDRESS = st.secrets["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = st.secrets["GMAIL_APP_PASSWORD"]


@st.cache_resource
def get_gemini_client():
    return genai.Client(api_key=GEMINI_API_KEY)


gemini_client = get_gemini_client()


def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})


def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        else:
            st.image(message["content"])


def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"


def extract_receipt(photo_bytes, mime_type):
    """Ask Gemini to turn a receipt photo into structured JSON."""
    try:
        response = gemini_client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=photo_bytes, mime_type=mime_type),
                "Extract this receipt.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=EXTRACT_PROMPT,
                response_mime_type="application/json",
            ),
        )
        text = response.text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(text), None
    except Exception as error:
        return None, str(error)


def looks_like_email(address):
    return "@" in address and "." in address.split("@")[-1] and " " not in address


def send_email(to_address, subject, body):
    try:
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = GMAIL_ADDRESS
        message["To"] = to_address
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(message)
        return True, "sent"
    except Exception as error:
        return False, str(error)


def clear_bill():
    st.session_state.base_df = empty_df()
    st.session_state.current_df = empty_df()
    st.session_state.tax = 0.0
    st.session_state.tip = 0.0
    st.session_state.bill_version += 1


# ---------- onboarding ----------
if "onboarded" not in st.session_state:
    st.title("🧾 ReceiptBuddy")
    st.caption("Snap it. Edit it. Split it. Email yourself the results.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        email = st.text_input(
            "Your email address",
            placeholder="you@example.com",
            help="This is where ReceiptBuddy will send your summary.",
        )
        names_text = st.text_input(
            "Names of the people splitting (optional, comma-separated)",
            placeholder="Priya, Rahul, Meera",
            help="Leave blank to just say how many people below.",
        )
        count = st.number_input("Number of people (if you left names blank)", 1, 50, 2)
        currency = st.text_input("Currency symbol", value="₹")
        submitted = st.form_submit_button("Let's go 🚀")

        if submitted:
            if not name.strip() or not email.strip():
                st.warning("Please fill in both your name and email.")
            elif not looks_like_email(email.strip()):
                st.warning("That email doesn't look right - please check it.")
            else:
                people = parse_names(names_text) or [
                    f"Person {i}" for i in range(1, int(count) + 1)
                ]
                st.session_state.name = name.strip()
                st.session_state.email = email.strip()
                st.session_state.people_names = ", ".join(people)
                st.session_state.currency = currency.strip() or "₹"
                st.session_state.tax = 0.0
                st.session_state.tip = 0.0
                st.session_state.base_df = empty_df()
                st.session_state.current_df = empty_df()
                st.session_state.bill_version = 0
                st.session_state.chat = gemini_client.chats.create(
                    model=MODEL_NAME,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
                )
                st.session_state.messages = [
                    {
                        "role": "assistant",
                        "kind": "text",
                        "content": WELCOME_MESSAGE_TEMPLATE.format(name=name.strip()),
                    }
                ]
                st.session_state.onboarded = True
                st.rerun()
    st.stop()

# ---------- handle new chat input (before any widgets are drawn) ----------
user_input = st.chat_input(
    "Attach a receipt photo, or ask a question",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        with st.spinner("Reading your receipt..."):
            data, error = extract_receipt(photo_bytes, photo.type)
        if error:
            add_message("assistant", "text", f"Sorry, I couldn't read that: {error}")
        elif not data.get("items"):
            add_message(
                "assistant",
                "text",
                "I couldn't find any items in that photo. Try a clearer, "
                "well-lit picture, or add the items by hand in the Edit and split tab.",
            )
        else:
            new_rows = pd.DataFrame(
                [
                    {"Item": str(i.get("name", "")), "Price": i.get("price"), "Who had it": ""}
                    for i in data["items"]
                ]
            )
            current = clean_df(st.session_state.current_df)
            st.session_state.base_df = clean_df(pd.concat([current, new_rows], ignore_index=True))
            st.session_state.tax = float(st.session_state.tax) + float(data.get("tax") or 0)
            st.session_state.tip = float(st.session_state.tip) + float(data.get("tip") or 0)
            if data.get("currency"):
                st.session_state.currency = str(data["currency"])
            st.session_state.bill_version += 1

            read_sum = sum(float(i.get("price") or 0) for i in data["items"])
            read_total = read_sum + float(data.get("tax") or 0) + float(data.get("tip") or 0)
            msg = f"Read {len(data['items'])} items" + (
                f" from {data['store']}" if data.get("store") else ""
            )
            msg += f", about {read_total:,.2f} in total. Check everything in the Edit and split tab."
            if data.get("total") and abs(float(data["total"]) - read_total) > 1:
                msg += (
                    f" Heads up: the receipt says {float(data['total']):,.2f}, so "
                    "I may have missed or misread something."
                )
            add_message("assistant", "text", msg)

    if text:
        add_message("user", "text", text)
        people_now = parse_names(st.session_state.people_names) or ["Person 1"]
        context = bill_context(
            st.session_state.current_df,
            people_now,
            st.session_state.tax,
            st.session_state.tip,
            st.session_state.currency,
        )
        with st.spinner("Thinking..."):
            answer = ask_gemini([f"{context}\n\nUser message: {text}"])
        add_message("assistant", "text", answer)

# ---------- main page ----------
st.title("🧾 ReceiptBuddy")
st.caption(
    f"Logged in as {st.session_state.name} - summary goes to {st.session_state.email}"
)

tab_chat, tab_edit = st.tabs(["Scan and chat", "Edit and split"])

with tab_chat:
    for message in st.session_state.messages:
        render_message(message)

with tab_edit:
    st.subheader("Who's splitting, tax and tip")
    st.text_input(
        "People (comma-separated names)",
        key="people_names",
        help="Add or remove names any time. The split updates instantly.",
    )
    col_tax, col_tip, col_cur = st.columns(3)
    col_tax.number_input("Tax", min_value=0.0, step=1.0, format="%.2f", key="tax")
    col_tip.number_input("Tip / service charge", min_value=0.0, step=1.0, format="%.2f", key="tip")
    col_cur.text_input("Currency symbol", key="currency")

    people = parse_names(st.session_state.people_names)
    if not people:
        st.warning("Add at least one name above.")
        people = ["Person 1"]

    st.subheader("Items")
    st.caption(
        "Click any cell to edit. Use the + row at the bottom to add an item, or select "
        "a row and press Delete to remove it. In 'Who had it', type names from your "
        "people list (e.g. Priya, Rahul); leave blank if everyone shared it."
    )
    edited = st.data_editor(
        st.session_state.base_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{st.session_state.bill_version}",
        column_config={
            "Item": st.column_config.TextColumn("Item"),
            "Price": st.column_config.NumberColumn("Price", min_value=0.0, format="%.2f"),
            "Who had it": st.column_config.TextColumn(
                "Who had it", help="Blank = shared by everyone"
            ),
        },
    )
    st.session_state.current_df = edited

    currency = st.session_state.currency
    result = compute_split(edited, people, st.session_state.tax, st.session_state.tip)
    for warning in result["warnings"]:
        st.warning(warning)

    st.subheader("Split")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Subtotal", money(result["subtotal"], currency))
    m2.metric("Tax", money(result["tax"], currency))
    m3.metric("Tip", money(result["tip"], currency))
    m4.metric("Total", money(result["total"], currency))
    st.table(
        pd.DataFrame(
            {
                "Person": list(result["per_person"].keys()),
                "Owes": [money(v, currency) for v in result["per_person"].values()],
            }
        ).set_index("Person")
    )

    summary = build_summary(
        st.session_state.name, edited, people, st.session_state.tax,
        st.session_state.tip, currency,
    )
    b1, b2, b3 = st.columns(3)
    if b1.button("📧 Email me the summary", use_container_width=True):
        if len(clean_df(edited)) == 0:
            st.warning("Add at least one item first.")
        else:
            with st.spinner("Sending..."):
                ok, info = send_email(
                    st.session_state.email, "Your ReceiptBuddy expense summary", summary
                )
            if ok:
                st.success("Sent! Check your inbox 📬")
            else:
                st.error(f"Couldn't send that: {info}")
    b2.download_button(
        "Download summary", summary, file_name="receipt-summary.txt", use_container_width=True
    )
    b3.button("Clear bill", on_click=clear_bill, use_container_width=True)
