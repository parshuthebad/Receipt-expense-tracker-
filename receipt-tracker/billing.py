"""Pure bill logic (no Streamlit), so it is easy to test."""
import pandas as pd

COLUMNS = ["Item", "Price", "Who had it"]


def empty_df():
    return pd.DataFrame(
        {
            "Item": pd.Series(dtype="str"),
            "Price": pd.Series(dtype="float"),
            "Who had it": pd.Series(dtype="str"),
        }
    )


def parse_names(text):
    seen, names = set(), []
    for part in str(text or "").split(","):
        name = part.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def clean_df(df):
    """Drop blank rows, make Price numeric, keep the 3 columns."""
    if df is None or len(df) == 0:
        return empty_df()
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df["Item"] = df["Item"].fillna("").astype(str).str.strip()
    df["Who had it"] = df["Who had it"].fillna("").astype(str).str.strip()
    keep = (df["Item"] != "") | df["Price"].notna()
    df = df[keep].copy()
    df["Price"] = df["Price"].fillna(0.0).astype(float)
    return df[COLUMNS].reset_index(drop=True)


def compute_split(df, people, tax, tip):
    """Split items between people. Blank 'Who had it' = shared by everyone.
    Tax and tip are shared in proportion to what each person's items cost."""
    df = clean_df(df)
    lookup = {p.lower(): p for p in people}
    subtotals = {p: 0.0 for p in people}
    warnings = []

    for _, row in df.iterrows():
        named = parse_names(row["Who had it"])
        eaters = [lookup[n.lower()] for n in named if n.lower() in lookup]
        unknown = [n for n in named if n.lower() not in lookup]
        if unknown:
            warnings.append(
                f"'{row['Item'] or 'Unnamed item'}': {', '.join(unknown)} "
                "not in the people list."
            )
        if not eaters:
            eaters = list(people)
        share = row["Price"] / len(eaters)
        for person in eaters:
            subtotals[person] += share

    base = sum(subtotals.values())
    extras = float(tax) + float(tip)
    totals = {}
    for person in people:
        if base > 0:
            totals[person] = subtotals[person] + extras * subtotals[person] / base
        else:
            totals[person] = extras / len(people)

    return {
        "subtotal": base,
        "tax": float(tax),
        "tip": float(tip),
        "total": base + extras,
        "per_person": totals,
        "warnings": warnings,
    }


def money(value, currency):
    return f"{currency}{value:,.2f}"


def build_summary(name, df, people, tax, tip, currency):
    df = clean_df(df)
    result = compute_split(df, people, tax, tip)
    lines = [f"Expense summary for {name}", "", "Items:"]
    if len(df) == 0:
        lines.append("- (no items)")
    for _, row in df.iterrows():
        who = row["Who had it"] or "everyone"
        lines.append(f"- {row['Item'] or 'Unnamed item'}: {money(row['Price'], currency)} ({who})")
    lines += [
        "",
        f"Subtotal: {money(result['subtotal'], currency)}",
        f"Tax: {money(result['tax'], currency)}",
        f"Tip: {money(result['tip'], currency)}",
        f"Total: {money(result['total'], currency)}",
        "",
        f"Split between {len(people)} people:",
    ]
    for person, amount in result["per_person"].items():
        lines.append(f"- {person}: {money(amount, currency)}")
    return "\n".join(lines)


def bill_context(df, people, tax, tip, currency):
    """Plain-text bill state handed to Gemini with each chat question."""
    df = clean_df(df)
    if len(df) == 0:
        return "Current bill: empty (no items yet)."
    return "Current bill (as edited by the user):\n" + build_summary(
        "user", df, people, tax, tip, currency
    )
