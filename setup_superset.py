#!/usr/bin/env python3
"""
scripts/setup_superset_v2.py

Phiên bản 2 — đã fix 2 lỗi:

(1) Lỗi "There is no chart definition associated with this component":
    Trong Superset 3.0, endpoint POST/PUT /api/v1/dashboard/ KHÔNG tự động
    extract chartId từ position_json để insert vào bảng dashboard_slices.
    → Sau khi tạo dashboard, gọi PUT /api/v1/chart/{chart_id} với
       {"dashboards": [..., dashboard_id]} để cập nhật quan hệ m2m.

(2) Lỗi "Unexpected Error" trên 2 chart "Enrollment by Program" và
    "Student Mobility by Institution":
    viz_type "echarts_bar" KHÔNG tồn tại trong Superset 3.0 → frontend
    crash. Các viz_type bar chart hợp lệ là: dist_bar (legacy, dùng cho
    categorical), echarts_timeseries_bar (modern). Đã đổi sang "dist_bar"
    vì purpose-built cho categorical bar chart.

Bonus: build_charts() giờ cũng PUT để update params của chart đã tồn tại,
khiến script idempotent — chạy lại nhiều lần luôn hội tụ về state đúng.

Usage:
    python scripts/setup_superset_v2.py
"""

import json
import time
import sys
import requests

SUPERSET_URL = "http://localhost:8088"
ADMIN_USER   = "admin"
ADMIN_PASS   = "admin"
DB_NAME      = "ednet_db"
DB_URI       = "postgresql://ednet:ednet_secret@postgres:5432/ednet_db"

session = requests.Session()


# ── Auth ──────────────────────────────────────────────────────────────────────

def login():
    print("[1/6] Logging in to Superset...")
    r = session.post(
        f"{SUPERSET_URL}/api/v1/security/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS,
              "provider": "db", "refresh": True},
    )
    if r.status_code != 200:
        print(f"  ERROR: Login failed ({r.status_code}): {r.text}")
        sys.exit(1)
    session.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})

    r = session.get(f"{SUPERSET_URL}/api/v1/security/csrf_token/")
    if r.status_code != 200:
        print(f"  ERROR: CSRF failed ({r.status_code}): {r.text}")
        sys.exit(1)
    session.headers.update({"X-CSRFToken": r.json()["result"], "Referer": SUPERSET_URL})
    print("  OK")


# ── Database ──────────────────────────────────────────────────────────────────

def create_database() -> int:
    print("[2/6] Creating database connection...")
    r = session.get(f"{SUPERSET_URL}/api/v1/database/")
    for db in r.json().get("result", []):
        if db["database_name"] == DB_NAME:
            print(f"  Already exists (id={db['id']}), skipping.")
            return db["id"]
    r = session.post(
        f"{SUPERSET_URL}/api/v1/database/",
        json={"database_name": DB_NAME, "sqlalchemy_uri": DB_URI,
              "expose_in_sqllab": True, "allow_run_async": False,
              "allow_ctas": False, "allow_cvas": False, "allow_dml": False},
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR: {r.status_code} {r.text}")
        sys.exit(1)
    db_id = r.json()["id"]
    print(f"  Created database id={db_id}")
    return db_id


# ── Datasets ──────────────────────────────────────────────────────────────────

DATASET_SQLS = {
    "kpi_summary": """
        SELECT v.value_id, v.kpi_id, d.name AS kpi_name, d.category, d.unit,
               d.target_threshold, d.alert_direction, v.scope_type, v.scope_id,
               v.period_start, v.period_end, v.value, v.computed_at,
               CASE
                   WHEN d.alert_direction = 'below' AND v.value < d.target_threshold THEN 'ALERT'
                   WHEN d.alert_direction = 'above' AND v.value > d.target_threshold THEN 'ALERT'
                   ELSE 'OK'
               END AS status
        FROM kpi_values v
        JOIN kpi_definitions d ON v.kpi_id = d.kpi_id
    """,
    "institution_map": """
        SELECT i.institution_id, i.name, i.country, i.type, i.joined_date,
               nm.role, nm.network_id
        FROM institutions i
        JOIN network_memberships nm ON i.institution_id = nm.institution_id
    """,
    "event_activity": """
        SELECT e.event_id, e.name AS event_name, e.type AS event_type,
               e.event_date, e.network_id,
               COUNT(DISTINCT ep.institution_id) AS institution_count,
               SUM(ep.participant_count) AS total_participants
        FROM events e
        JOIN event_participants ep ON e.event_id = ep.event_id
        GROUP BY e.event_id, e.name, e.type, e.event_date, e.network_id
    """,
    "enrollment_summary": """
        SELECT en.enrollment_id, en.student_id, en.program_id,
               p.name AS program_name, p.field, p.language AS program_language,
               p.status AS program_status, p.host_institution_id,
               en.enrolled_date, en.status AS enrollment_status,
               en.outcome, en.completion_date
        FROM enrollments en
        JOIN programs p ON en.program_id = p.program_id
    """,
    "mobility_summary": """
        SELECT mr.mobility_id, mr.person_type, mr.from_institution_id,
               mr.to_institution_id,
               i_to.name AS to_institution_name,
               i_from.name AS from_institution_name,
               mr.modality, mr.start_date, mr.end_date, mr.program_id
        FROM mobility_records mr
        JOIN institutions i_to   ON mr.to_institution_id   = i_to.institution_id
        JOIN institutions i_from ON mr.from_institution_id = i_from.institution_id
    """,
}


def create_datasets(db_id: int) -> dict[str, int]:
    print("[3/6] Creating datasets...")
    r = session.get(f"{SUPERSET_URL}/api/v1/dataset/?q=(page_size:100)")
    existing = {d["table_name"]: d["id"] for d in r.json().get("result", [])}
    ids = {}
    for name, sql in DATASET_SQLS.items():
        if name in existing:
            print(f"  Dataset '{name}' already exists (id={existing[name]}), skipping.")
            ids[name] = existing[name]
            continue
        r = session.post(
            f"{SUPERSET_URL}/api/v1/dataset/",
            json={"database": db_id, "schema": "public", "table_name": name,
                  "sql": sql.strip(), "is_managed_externally": False},
        )
        if r.status_code not in (200, 201):
            print(f"  ERROR creating dataset '{name}': {r.status_code} {r.text[:200]}")
            continue
        ds_id = r.json()["id"]
        ids[name] = ds_id
        print(f"  Created dataset '{name}' (id={ds_id})")
    return ids


# ── Charts ────────────────────────────────────────────────────────────────────

def build_chart_defs(ds: dict[str, int]) -> list:
    return [
        {
            "slice_name": "KPI Status Overview",
            "viz_type": "table",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "all_columns": ["kpi_id", "kpi_name", "category", "value",
                                "target_threshold", "unit", "status"],
                "order_by_cols": [], "adhoc_filters": [],
                "row_limit": 20, "include_time": False,
            },
        },
        {
            "slice_name": "K01 - Network Participation Rate",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K01"}],
                "subheader": "Target: >= 80%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K02 - Collaboration Index",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K02"}],
                "subheader": "Target: >= 30%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K03 - Student Mobility Rate",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K03"}],
                "subheader": "Target: >= 15%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K04 - Joint Event Frequency",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K04"}],
                "subheader": "Target: >= 4 per semester", "y_axis_format": ",.0f",
            },
        },
        {
            "slice_name": "Institution Type Breakdown",
            "viz_type": "pie",
            "datasource_id": ds["institution_map"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "institution_id", "type": "INT"},
                           "aggregate": "COUNT", "label": "Count"},
                "groupby": ["type"], "adhoc_filters": [],
                "row_limit": 10, "donut": True, "show_labels": True,
            },
        },
        {
            "slice_name": "Event Activity by Month",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": ds["event_activity"],
            "params": {
                "metrics": [{"expressionType": "SIMPLE",
                             "column": {"column_name": "event_id", "type": "INT"},
                             "aggregate": "COUNT", "label": "Events"}],
                "groupby": ["event_type"],
                "granularity_sqla": "event_date",
                "time_grain_sqla": "P1M",
                "adhoc_filters": [], "row_limit": 1000,
                "stack": True, "x_axis": "event_date",
            },
        },
        {
            "slice_name": "Institution Count by Country",
            "viz_type": "table",
            "datasource_id": ds["institution_map"],
            "params": {
                "metrics": [{"expressionType": "SIMPLE",
                             "column": {"column_name": "institution_id", "type": "INT"},
                             "aggregate": "COUNT", "label": "Institutions"}],
                "groupby": ["country"], "adhoc_filters": [],
                "row_limit": 20, "include_time": False,
            },
        },
        {
            "slice_name": "K05 - Program Completion Rate",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K05"}],
                "subheader": "Target: >= 75%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K06 - Student Withdrawal Rate",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K06"}],
                "subheader": "Target: <= 10%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K07 - Multilingual Program Coverage",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Value"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K07"}],
                "subheader": "Target: >= 25%", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "All KPIs vs Target",
            "viz_type": "table",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "all_columns": ["kpi_id", "kpi_name", "category", "value",
                                "target_threshold", "unit", "status"],
                "order_by_cols": [], "adhoc_filters": [],
                "row_limit": 20, "include_time": False,
            },
        },
        # ── FIX: "echarts_bar" KHÔNG tồn tại trong Superset 3.0 → đổi sang
        # "dist_bar" (Distribution Bar Chart, purpose-built cho categorical).
        # "groupby" đóng vai trò trục X (dimension), bỏ "x_axis" vì dist_bar
        # không dùng field này.
        {
            "slice_name": "Enrollment by Program",
            "viz_type": "dist_bar",
            "datasource_id": ds["enrollment_summary"],
            "params": {
                "metrics": [{"expressionType": "SIMPLE",
                             "column": {"column_name": "enrollment_id", "type": "INT"},
                             "aggregate": "COUNT", "label": "Enrollments"}],
                "groupby": ["program_name"],
                "columns": [],
                "adhoc_filters": [],
                "row_limit": 20,
                "order_desc": True,
                "show_legend": False,
                "y_axis_format": ",.0f",
                "bottom_margin": "auto",
                "x_ticks_layout": "45°",
            },
        },
        {
            "slice_name": "K09 - HITL Turnaround Time",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Avg Hours"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K09"}],
                "subheader": "Target: <= 48 hours", "y_axis_format": ",.1f",
            },
        },
        {
            "slice_name": "K10 - Ethics Compliance Rate",
            "viz_type": "big_number_total",
            "datasource_id": ds["kpi_summary"],
            "params": {
                "metric": {"expressionType": "SIMPLE",
                           "column": {"column_name": "value", "type": "NUMERIC"},
                           "aggregate": "AVG", "label": "Compliance (%)"},
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "kpi_id", "operator": "==",
                                   "comparator": "K10"}],
                "subheader": "Target: >= 95%", "y_axis_format": ",.1f",
            },
        },
        # ── FIX: cùng lý do — đổi "echarts_bar" → "dist_bar"
        {
            "slice_name": "Student Mobility by Institution",
            "viz_type": "dist_bar",
            "datasource_id": ds["mobility_summary"],
            "params": {
                "metrics": [{"expressionType": "SIMPLE",
                             "column": {"column_name": "mobility_id", "type": "INT"},
                             "aggregate": "COUNT", "label": "Count"}],
                "groupby": ["to_institution_name"],
                "columns": [],
                "adhoc_filters": [{"expressionType": "SIMPLE", "clause": "WHERE",
                                   "subject": "person_type", "operator": "==",
                                   "comparator": "student"}],
                "row_limit": 20,
                "order_desc": True,
                "show_legend": False,
                "y_axis_format": ",.0f",
                "bottom_margin": "auto",
                "x_ticks_layout": "45°",
            },
        },
    ]


def build_charts(ds: dict[str, int]) -> dict[str, int]:
    """
    Tạo charts. Nếu chart đã tồn tại (cùng slice_name) thì PUT cập nhật
    viz_type/params — giúp script idempotent: chạy lại nhiều lần luôn
    converge về đúng config trong build_chart_defs, không bị stuck ở
    config cũ. KHÔNG truyền "dashboards" trong PUT để giữ nguyên m2m
    association có sẵn.
    """
    print("[4/6] Creating / updating charts...")

    r = session.get(f"{SUPERSET_URL}/api/v1/chart/?q=(page_size:200)")
    existing = {c["slice_name"]: c["id"] for c in r.json().get("result", [])}

    charts = {}
    for chart in build_chart_defs(ds):
        name = chart["slice_name"]

        if name in existing:
            chart_id = existing[name]
            put_payload = {
                "slice_name":      name,
                "viz_type":        chart["viz_type"],
                "datasource_id":   chart["datasource_id"],
                "datasource_type": "table",
                "params":          json.dumps(chart["params"]),
            }
            r = session.put(
                f"{SUPERSET_URL}/api/v1/chart/{chart_id}",
                json=put_payload,
            )
            if r.status_code in (200, 201):
                print(f"  Updated chart '{name}' (id={chart_id})")
            else:
                print(f"  WARN update '{name}': {r.status_code} {r.text[:120]}")
            charts[name] = chart_id
            continue

        # POST create new
        post_payload = {
            "slice_name":      name,
            "viz_type":        chart["viz_type"],
            "datasource_id":   chart["datasource_id"],
            "datasource_type": "table",
            "params":          json.dumps(chart["params"]),
            "cache_timeout":   None,
        }
        r = session.post(f"{SUPERSET_URL}/api/v1/chart/", json=post_payload)
        if r.status_code not in (200, 201):
            print(f"  WARN create '{name}': {r.status_code} {r.text[:120]}")
            continue
        chart_id = r.json()["id"]
        charts[name] = chart_id
        print(f"  Created chart '{name}' (id={chart_id})")

    return charts


# ── Position JSON builder ─────────────────────────────────────────────────────

def build_position(rows_config: list, charts: dict[str, int]) -> str:
    pos = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "type": "ROOT", "id": "ROOT_ID",
            "children": ["GRID_ID"],
            "parents": [],
        },
        "GRID_ID": {
            "type": "GRID", "id": "GRID_ID",
            "children": [rc[0] for rc in rows_config],
            "parents": ["ROOT_ID"],
        },
    }

    for row_id, comps in rows_config:
        comp_ids = [c[0] for c in comps]
        pos[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": comp_ids,
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT", "isCollapsed": False},
        }
        for comp_id, chart_name, w, h in comps:
            chart_id = charts.get(chart_name, 0)
            pos[comp_id] = {
                "type": "CHART",
                "id": comp_id,
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "meta": {
                    "chartId": chart_id,
                    "sliceName": chart_name,
                    "width": w,
                    "height": h,
                },
            }

    return json.dumps(pos)


# ── Chart ⇄ Dashboard linking ────────────────────────────────────────────────

def get_chart_current_dashboards(chart_id: int) -> list:
    r = session.get(f"{SUPERSET_URL}/api/v1/chart/{chart_id}")
    if r.status_code != 200:
        return []
    result = r.json().get("result", {})
    return [d["id"] for d in result.get("dashboards", [])]


def link_chart_to_dashboard(chart_id: int, dashboard_id: int) -> bool:
    """
    Liên kết chart với dashboard qua PUT /api/v1/chart/{id} — cập nhật
    quan hệ m2m, trigger insert vào bảng dashboard_slices.
    """
    current = get_chart_current_dashboards(chart_id)
    if dashboard_id in current:
        return True
    current.append(dashboard_id)
    r = session.put(
        f"{SUPERSET_URL}/api/v1/chart/{chart_id}",
        json={"dashboards": current},
    )
    if r.status_code not in (200, 201):
        print(f"    WARN: link chart_id={chart_id} -> dashboard_id={dashboard_id}: "
              f"{r.status_code} {r.text[:120]}")
        return False
    return True


# ── Dashboards ────────────────────────────────────────────────────────────────

def find_dashboard_by_slug(slug: str):
    r = session.get(f"{SUPERSET_URL}/api/v1/dashboard/?q=(page_size:100)")
    if r.status_code != 200:
        return None
    for d in r.json().get("result", []):
        if d.get("slug") == slug:
            return d["id"]
    return None


def create_dashboards(charts: dict[str, int]):
    print("[5/6] Creating dashboards...")

    def create_one(title: str, slug: str, rows_config: list):
        position = build_position(rows_config, charts)

        chart_names_in_dash = [c[1] for _row_id, comps in rows_config for c in comps]
        chart_ids_in_dash = [charts[name] for name in chart_names_in_dash
                             if name in charts]

        existing_id = find_dashboard_by_slug(slug)
        if existing_id is not None:
            dashboard_id = existing_id
            print(f"  Dashboard '{title}' already exists (id={dashboard_id}), reusing.")
        else:
            r = session.post(
                f"{SUPERSET_URL}/api/v1/dashboard/",
                json={
                    "dashboard_title": title,
                    "slug": slug,
                    "position_json": position,
                    "published": True,
                },
            )
            if r.status_code not in (200, 201):
                print(f"  WARN create '{title}': {r.status_code} {r.text[:200]}")
                return
            dashboard_id = r.json()["id"]
            print(f"  Created '{title}' (id={dashboard_id})")

        print(f"  Linking {len(chart_ids_in_dash)} charts to dashboard...")
        linked = 0
        for chart_id in chart_ids_in_dash:
            if link_chart_to_dashboard(chart_id, dashboard_id):
                linked += 1
        print(f"  Linked {linked}/{len(chart_ids_in_dash)} charts to '{title}'")

        r2 = session.put(
            f"{SUPERSET_URL}/api/v1/dashboard/{dashboard_id}",
            json={
                "dashboard_title": title,
                "position_json": position,
                "published": True,
            },
        )
        if r2.status_code not in (200, 201):
            print(f"  WARN update '{title}': {r2.status_code} {r2.text[:200]}")
        else:
            print(f"  Final position_json synced for '{title}'")

    # ── Dashboard 1: Network Overview ──────────────────────────────────────
    d1_rows = [
        ("ROW-1", [
            ("CHART-1", "K01 - Network Participation Rate", 3, 18),
            ("CHART-2", "K02 - Collaboration Index",         3, 18),
            ("CHART-3", "K03 - Student Mobility Rate",       3, 18),
            ("CHART-4", "K04 - Joint Event Frequency",       3, 18),
        ]),
        ("ROW-2", [
            ("CHART-5", "Institution Count by Country",      4, 36),
            ("CHART-6", "Institution Type Breakdown",        8, 36),
        ]),
        ("ROW-3", [
            ("CHART-7", "Event Activity by Month",           8, 36),
            ("CHART-8", "KPI Status Overview",               4, 36),
        ]),
    ]
    create_one("VASTN - Network Overview", "network-overview", d1_rows)

    # ── Dashboard 2: Program Performance ──────────────────────────────────
    d2_rows = [
        ("ROW-A", [
            ("CHART-A1", "K05 - Program Completion Rate",       4, 18),
            ("CHART-A2", "K06 - Student Withdrawal Rate",       4, 18),
            ("CHART-A3", "K07 - Multilingual Program Coverage", 4, 18),
        ]),
        ("ROW-B", [
            ("CHART-B1", "All KPIs vs Target",                 12, 36),
        ]),
        ("ROW-C", [
            ("CHART-C1", "Enrollment by Program",               6, 36),
            ("CHART-C2", "Student Mobility by Institution",     6, 36),
        ]),
        ("ROW-D", [
            ("CHART-D1", "K09 - HITL Turnaround Time",          6, 18),
            ("CHART-D2", "K10 - Ethics Compliance Rate",        6, 18),
        ]),
    ]
    create_one("VASTN - Program Performance", "program-performance", d2_rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def wait_for_superset():
    print("[0/6] Waiting for Superset to be ready...")
    for i in range(30):
        try:
            r = requests.get(f"{SUPERSET_URL}/health", timeout=3)
            if r.status_code == 200:
                print("  Superset is up.")
                return
        except Exception:
            pass
        print(f"  Waiting... ({i+1}/30)")
        time.sleep(3)
    print("  ERROR: Superset did not respond in time.")
    sys.exit(1)


def main():
    wait_for_superset()
    login()
    db_id  = create_database()
    ds     = create_datasets(db_id)
    charts = build_charts(ds)
    create_dashboards(charts)

    print("\n[6/6] Done!")
    print("")
    print("Superset   : http://localhost:8088  (admin / admin)")
    print("Dashboard 1: http://localhost:8088/superset/dashboard/network-overview/")
    print("Dashboard 2: http://localhost:8088/superset/dashboard/program-performance/")


if __name__ == "__main__":
    main()
