# doc_generator/management/commands/import_mapping.py
import re
from django.core.management.base import BaseCommand
from django.db import transaction
import pandas as pd

from doc_generator.models import Control, PolicyTemplate

# Heuristic column name options
POLICY_NAME_COLS = ["policy name", "policy", "document name", "document", "policy_title", "policy_name"]
POLICY_DESC_COLS = ["policy description", "description", "doc description", "document description"]
MAPPED_CONTROLS_COLS = ["mapped controls", "controls", "mapped_control", "mapped_controls", "controls_mapped", "annex controls", "annex"]

def find_column(cols, candidates):
    cols_lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand in cols_lower:
            return cols_lower[cand]
    # partial matches
    for cand in candidates:
        for col in cols_lower:
            if cand in col:
                return cols_lower[col]
    return None

# regex patterns
# match single control like A.6.1 or A.8.24
SINGLE_CTRL_RE = re.compile(r"\bA\.\d+(?:\.\d+)?\b", flags=re.IGNORECASE)
# match a range like A.6.1 - A.6.4 or A.6.1–A.6.4 (various dash chars)
RANGE_RE = re.compile(r"\b(A\.\d+(?:\.\d+)?)\s*[-–—]\s*(A\.\d+(?:\.\d+)?)\b", flags=re.IGNORECASE)

def normalize_ctrl_id(raw: str) -> str:
    """Normalize control id formatting: remove spaces, unify case, e.g., 'a.6.1' -> 'A.6.1'"""
    if not raw:
        return raw
    s = raw.strip()
    s = s.replace(" ", "")
    # ensure uppercase A
    s = re.sub(r"^a\.", "A.", s, flags=re.IGNORECASE)
    return s

def expand_range(start: str, end: str):
    """
    Expand a range start..end inclusive.
    Both start and end should match SINGLE_CTRL_RE.
    Works when the left-most numeric prefix (after 'A.') matches for all but the last numeric part.
    Examples:
      A.6.1 - A.6.4 -> A.6.1, A.6.2, A.6.3, A.6.4
      A.8.24 - A.8.28 -> A.8.24..A.8.28
    If formats differ or cannot expand, returns [start, end].
    """
    s = normalize_ctrl_id(start)
    e = normalize_ctrl_id(end)

    # extract numeric parts after 'A.'
    def parts(ctrl):
        nums = ctrl.split('.')[1:]  # drop leading 'A'
        try:
            return [int(x) for x in nums]
        except ValueError:
            return None

    sp = parts(s)
    ep = parts(e)
    if sp is None or ep is None:
        return [s, e]

    # if lengths differ (e.g., A.6 and A.6.4) -- fallback
    if len(sp) != len(ep):
        # If end has extra granularity but prefix matches, try to expand on last number of end only when start is prefix
        if len(sp) < len(ep) and sp == ep[:len(sp)]:
            # e.g., start A.6 -> ep [6,4] start [6] -> not supported reliably
            return [s, e]
        return [s, e]

    # ensure all prefix parts except last match
    if sp[:-1] != ep[:-1]:
        return [s, e]

    start_num = sp[-1]
    end_num = ep[-1]

    if end_num < start_num:
        return [s, e]

    base_prefix = "A." + ".".join(str(x) for x in sp[:-1]) if len(sp) > 1 else "A"
    results = []
    # construct each control: keep the prefix(s) then the iterated last number
    if len(sp) == 1:
        # unusual: A.<n> format (rare). handle as A.<n> .. A.<m>
        for i in range(start_num, end_num + 1):
            results.append(f"A.{i}")
    else:
        prefix = "A." + ".".join(str(x) for x in sp[:-1])
        for i in range(start_num, end_num + 1):
            results.append(f"{prefix}.{i}")
    return results

def split_control_cell(cell):
    """
    Given the raw cell text, return a list of normalized control IDs.
    Handles:
      - comma/semicolon/newline separated lists
      - entries with titles: 'A.8.24 – Secure coding'
      - ranges: 'A.6.1 - A.6.4' (expanded)
    """
    if pd.isna(cell):
        return []

    # unify separators to comma
    txt = str(cell).strip()
    # replace slashes/newlines/semicolons with comma
    txt = re.sub(r"[;/\n\r]+", ",", txt)
    # also replace ' – ' and similar with '-' for range detection consistency
    # but keep both patterns: RANGE_RE handles en-dash
    parts = [p.strip() for p in txt.split(",") if p.strip()]

    controls = []
    for part in parts:
        # First, check for explicit range anywhere in the token
        range_match = RANGE_RE.search(part)
        if range_match:
            s = range_match.group(1)
            e = range_match.group(2)
            expanded = expand_range(s, e)
            for ctrl in expanded:
                controls.append(normalize_ctrl_id(ctrl))
            # Also check if token contained additional singular IDs after range (unlikely) - continue to next part
            continue

        # Otherwise, find all single control ids inside the token (handles 'A.8.24 - Secure coding' by matching the id)
        singles = SINGLE_CTRL_RE.findall(part)
        if singles:
            for s in singles:
                controls.append(normalize_ctrl_id(s))
            continue

        # If nothing matched, try to salvage numeric ranges like 'A.6.1-A.6.4' without spaces
        compact_range = re.findall(r"(A\.\d+(?:\.\d+)?)[-–—](A\.\d+(?:\.\d+)?)", part)
        if compact_range:
            for s, e in compact_range:
                expanded = expand_range(s, e)
                for ctrl in expanded:
                    controls.append(normalize_ctrl_id(ctrl))
            continue

        # fallback: if token looks like e.g., 'A6.1' or 'A 6.1' try to extract digits
        alt = re.findall(r"A[\s\.]?(\d+)[\s\.\-]?(\d+)?", part, flags=re.IGNORECASE)
        if alt:
            # build plausible control ids from matches
            for a in alt:
                if a[1]:
                    controls.append(f"A.{a[0]}.{a[1]}")
                else:
                    controls.append(f"A.{a[0]}")
            continue

        # unable to parse this token -> skip
        # (optionally log or collect unparsed tokens)
        continue

    # deduplicate while preserving order
    seen = set()
    deduped = []
    for c in controls:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


class Command(BaseCommand):
    help = "Import control -> policy mapping from an Excel file into Control and PolicyTemplate models."

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help="Path to the Excel file (xlsx/xls/csv)")
        parser.add_argument('--sheet', type=str, default=None, help="Sheet name or index (optional)")
        parser.add_argument('--dry-run', action='store_true', help="Parse and show summary without writing to DB")

    def handle(self, *args, **options):
        path = options['path']
        sheet = options.get('sheet')
        dry_run = options.get('dry_run', False)

        # read file
        try:
            if path.lower().endswith(".csv"):
                df = pd.read_csv(path, dtype=str)
            else:
                if sheet is None:
                    df = pd.read_excel(path, sheet_name=0, dtype=str)
                else:
                    try:
                        idx = int(sheet)
                        df = pd.read_excel(path, sheet_name=idx, dtype=str)
                    except ValueError:
                        df = pd.read_excel(path, sheet_name=sheet, dtype=str)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to read file: {e}"))
            return

        if df.empty:
            self.stderr.write(self.style.ERROR("No rows found in file."))
            return

        cols = list(df.columns)
        policy_col = find_column(cols, POLICY_NAME_COLS)
        desc_col = find_column(cols, POLICY_DESC_COLS)
        mapped_col = find_column(cols, MAPPED_CONTROLS_COLS)

        if not policy_col:
            self.stderr.write(self.style.ERROR(f"Couldn't find a policy name column. Found columns: {cols}"))
            return
        if not mapped_col:
            self.stderr.write(self.style.WARNING("Couldn't reliably find a mapped-controls column. Attempting to continue, but rows without mapped controls will be skipped."))

        self.stdout.write(self.style.NOTICE(f"Using columns -> Policy: '{policy_col}', Description: '{desc_col}', Mapped Controls: '{mapped_col}'"))

        preview_rows = []
        for idx, row in df.iterrows():
            pname = str(row.get(policy_col) or "").strip()
            if not pname:
                continue
            pdesc = str(row.get(desc_col) or "").strip() if desc_col else ""
            mapped_cell = row.get(mapped_col) if mapped_col else None
            control_ids = split_control_cell(mapped_cell) if mapped_col else []
            preview_rows.append((pname, pdesc, control_ids))

        # show preview
        self.stdout.write(self.style.SQL_TABLE("Preview of parsed rows (first 15):"))
        for r in preview_rows[:15]:
            self.stdout.write(f" - {r[0]} -> {len(r[2])} controls -> {r[2]}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run completed. No DB changes made."))
            return

        created_policies = 0
        updated_policies = 0
        created_controls = 0
        skipped = 0

        with transaction.atomic():
            for pname, pdesc, control_ids in preview_rows:
                # create or update PolicyTemplate
                pt, created = PolicyTemplate.objects.get_or_create(name=pname, defaults={"description": pdesc})
                if created:
                    created_policies += 1
                else:
                    if pdesc and pt.description != pdesc:
                        pt.description = pdesc
                        pt.save()
                        updated_policies += 1

                pt.controls.clear()
                for cid in control_ids:
                    if not cid:
                        continue
                    ctrl, ccreated = Control.objects.get_or_create(control_id=cid, defaults={"title": cid})
                    if ccreated:
                        created_controls += 1
                    pt.controls.add(ctrl)
                pt.save()

        self.stdout.write(self.style.SUCCESS(f"Rows processed: {len(preview_rows)}"))
        self.stdout.write(self.style.SUCCESS(f"PolicyTemplates created: {created_policies}, updated: {updated_policies}"))
        self.stdout.write(self.style.SUCCESS(f"Controls created: {created_controls}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped rows with missing policy name: {skipped}"))
        self.stdout.write(self.style.SUCCESS("Import completed."))

