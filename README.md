# 🧾 ReceiptBuddy - Receipt & Expense Tracker / Bill Splitter

A Streamlit app. Snap a photo of a receipt (Gemini vision reads it), then
edit everything yourself: fix prices, add or delete items, say who had
what, change tax, tip and the list of people. The split updates instantly
and one button emails you the summary.

Built with: Python, Streamlit, Google Gemini, Gmail SMTP (free).

## What the user can change
- Items: edit any name or price, add rows with the + row, delete rows
- Who had it: type names per item (blank = shared by everyone)
- People: add or remove names any time
- Tax, tip and currency symbol
- Add more receipts: every new photo adds its items to the same bill
- Add items with no photo at all (manual entry)
- Ask the chat questions like "who owes the most?" - it sees your edited bill

Tax and tip are shared in proportion to what each person's items cost.

## Project structure
```
app.py                          the Streamlit app (UI, Gemini, email)
billing.py                      split / summary logic (no Streamlit)
prompts.py                      chat personality + receipt-extraction prompt
requirements.txt                dependencies
.gitignore                      keeps secrets out of GitHub
.streamlit/secrets.toml.example template for your keys
```

## Setup
1. `python -m venv venv` and activate it
2. `pip install -r requirements.txt`
3. Get a Gemini API key at aistudio.google.com -> Get API key
4. On the sending Gmail account, turn on 2-Step Verification, then create an
   App Password at myaccount.google.com/apppasswords
5. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in
6. `streamlit run app.py`

## Notes
- Never commit `secrets.toml` or use your real Gmail password - only the App Password.
- If the default model is unavailable to you, set `GEMINI_MODEL` in secrets.toml
  (e.g. `GEMINI_MODEL = "gemini-2.5-flash"`).
- Amounts are rounded to 2 decimals, so per-person totals can differ from the
  bill total by a paisa/cent.
