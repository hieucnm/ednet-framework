# data/seed_data.py
"""
Synthetic dataset generator for the EdNet framework prototype.
Generates a realistic 2-year dataset for one education network
with 8 member institutions across 4 countries.

Usage:
    python data/seed_data.py
    # or inside Docker:
    docker compose exec app python data/seed_data.py
"""

import os
import random
from datetime import date, timedelta
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
rng = random.Random(42)   # Fixed seed for reproducibility


# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def execute(conn, sql: str, params: dict | list):
    if isinstance(params, list):
        for p in params:
            conn.execute(text(sql), p)
    else:
        conn.execute(text(sql), params)


# ── Seed functions ────────────────────────────────────────────────────────────

def seed_network(conn) -> int:
    conn.execute(text("""
        INSERT INTO networks (name, type, established_date, description)
        VALUES (:name, :type, :established_date, :description)
    """), {
        "name": "Vietnam AI & Semiconductor Training Network (VASTN)",
        "type": "national",
        "established_date": date(2022, 6, 1),
        "description": (
            "A national network of universities and enterprises established "
            "to coordinate AI and semiconductor workforce training programs."
        ),
    })
    return conn.execute(text("SELECT MAX(network_id) FROM networks")).scalar()


def seed_institutions(conn, network_id: int) -> list[int]:
    institutions = [
        ("Ho Chi Minh City University of Technology (HCMUT)", "Vietnam",
         "university", date(2022, 6, 1), "coordinator"),
        ("Hanoi University of Science and Technology (HUST)", "Vietnam",
         "university", date(2022, 6, 1), "member"),
        ("Vietnam National University - HCM (VNU-HCM)", "Vietnam",
         "university", date(2022, 8, 1), "member"),
        ("FPT University", "Vietnam",
         "university", date(2022, 9, 1), "member"),
        ("National University of Singapore (NUS)", "Singapore",
         "university", date(2022, 11, 1), "member"),
        ("Intel Vietnam", "Vietnam",
         "enterprise", date(2023, 1, 1), "member"),
        ("Samsung R&D Vietnam", "Vietnam",
         "enterprise", date(2023, 3, 1), "member"),
        ("Synopsys Vietnam", "Vietnam",
         "enterprise", date(2023, 6, 1), "observer"),
    ]

    ids = []
    for name, country, inst_type, joined, role in institutions:
        conn.execute(text("""
            INSERT INTO institutions (name, country, type, joined_date)
            VALUES (:name, :country, :type, :joined_date)
        """), {"name": name, "country": country,
               "type": inst_type, "joined_date": joined})
        inst_id = conn.execute(
            text("SELECT MAX(institution_id) FROM institutions")
        ).scalar()
        conn.execute(text("""
            INSERT INTO network_memberships (network_id, institution_id, role, since_date)
            VALUES (:network_id, :institution_id, :role, :since_date)
        """), {"network_id": network_id, "institution_id": inst_id,
               "role": role, "since_date": joined})
        ids.append(inst_id)

    return ids  # [hcmut, hust, vnu, fpt, nus, intel, samsung, synopsys]


def seed_staff(conn, institution_ids: list[int]) -> list[int]:
    staff_pool = [
        ("Dr. Nguyen Minh Tuan",  "coordinator"),
        ("Prof. Tran Thi Lan",    "faculty"),
        ("Mr. Le Van Thanh",      "admin"),
        ("Prof. Sarah Chen",      "faculty"),
        ("Dr. Pham Quoc Hung",    "faculty"),
        ("Dr. Vu Thi Hoa",        "faculty"),
        ("Mr. David Tan",         "coordinator"),
        ("Dr. Le Hoang Nam",      "faculty"),
        ("Ms. Nguyen Phuong Anh", "admin"),
        ("Dr. Kim Ji-woo",        "faculty"),
    ]

    ids = []
    for i, (name, role) in enumerate(staff_pool):
        inst_id = institution_ids[i % len(institution_ids)]
        email = name.lower().replace(" ", ".").replace(".", "_") + "@ednet.test"
        conn.execute(text("""
            INSERT INTO staff (institution_id, name, role, email)
            VALUES (:institution_id, :name, :role, :email)
        """), {"institution_id": inst_id, "name": name,
               "role": role, "email": email})
        ids.append(conn.execute(
            text("SELECT MAX(staff_id) FROM staff")
        ).scalar())

    return ids


def seed_programs(
    conn, network_id: int,
    institution_ids: list[int],
    staff_ids: list[int],
) -> list[int]:
    programs = [
        ("Applied AI for Industry 4.0",
         institution_ids[0], "AI", "en",
         date(2023, 1, 15), date(2024, 12, 31), "active",
         [institution_ids[1], institution_ids[4], institution_ids[5]]),

        ("Semiconductor Design Fundamentals",
         institution_ids[1], "Semiconductor", "vi",
         date(2023, 3, 1), date(2025, 2, 28), "active",
         [institution_ids[0], institution_ids[6]]),

        ("Data Engineering and MLOps",
         institution_ids[2], "AI", "en",
         date(2023, 6, 1), date(2024, 5, 31), "completed",
         [institution_ids[3], institution_ids[4]]),

        ("Embedded Systems for IoT",
         institution_ids[3], "Semiconductor", "vi",
         date(2024, 1, 1), date(2025, 6, 30), "active",
         [institution_ids[0], institution_ids[7]]),

        ("AI Ethics and Governance",
         institution_ids[4], "AI", "en",
         date(2024, 3, 1), date(2025, 2, 28), "active",
         [institution_ids[0], institution_ids[1], institution_ids[2]]),
    ]

    program_ids = []
    for name, host, field, lang, start, end, status, partners in programs:
        conn.execute(text("""
            INSERT INTO programs
                (name, host_institution_id, network_id, start_date, end_date,
                 field, language, status)
            VALUES
                (:name, :host, :network_id, :start, :end, :field, :lang, :status)
        """), {"name": name, "host": host, "network_id": network_id,
               "start": start, "end": end, "field": field,
               "lang": lang, "status": status})
        pid = conn.execute(
            text("SELECT MAX(program_id) FROM programs")
        ).scalar()
        program_ids.append(pid)

        for partner_id in partners:
            conn.execute(text("""
                INSERT INTO program_partners (program_id, institution_id, role)
                VALUES (:pid, :inst_id, 'co-host')
            """), {"pid": pid, "inst_id": partner_id})

        # 3-5 courses per program
        modalities = ["online", "in-person", "hybrid"]
        for j in range(rng.randint(3, 5)):
            conn.execute(text("""
                INSERT INTO courses
                    (program_id, name, credits, language, modality, instructor_id)
                VALUES
                    (:pid, :name, :credits, :lang, :modality, :instructor_id)
            """), {
                "pid": pid,
                "name": f"Module {j+1}: {name} — Topic {j+1}",
                "credits": rng.choice([2, 3, 4]),
                "lang": lang,
                "modality": rng.choice(modalities),
                "instructor_id": rng.choice(staff_ids),
            })

    return program_ids


def seed_students_and_enrollments(
    conn, institution_ids: list[int], program_ids: list[int]
) -> list[int]:
    fields = ["Computer Science", "Electrical Engineering",
              "Data Science", "Electronics"]
    outcomes = ["pass", "pass", "pass", "fail", "incomplete"]  # weighted toward pass
    student_ids = []

    for i in range(120):
        inst_id = rng.choice(institution_ids[:5])  # students from universities only
        conn.execute(text("""
            INSERT INTO students
                (home_institution_id, name, enrollment_year, field_of_study)
            VALUES
                (:inst_id, :name, :year, :field)
        """), {
            "inst_id": inst_id,
            "name": f"Student_{i+1:03d}",
            "year": rng.randint(2022, 2024),
            "field": rng.choice(fields),
        })
        sid = conn.execute(
            text("SELECT MAX(student_id) FROM students")
        ).scalar()
        student_ids.append(sid)

        # Each student enrolls in 1-2 programs
        for pid in rng.sample(program_ids, k=rng.randint(1, 2)):
            is_completed = rng.random() < 0.75
            conn.execute(text("""
                INSERT INTO enrollments
                    (student_id, program_id, enrolled_date,
                     status, completion_date, outcome)
                VALUES
                    (:sid, :pid, :enrolled,
                     :status, :completion, :outcome)
            """), {
                "sid": sid,
                "pid": pid,
                "enrolled": rand_date(date(2023, 1, 1), date(2024, 6, 1)),
                "status": "completed" if is_completed else "ongoing",
                "completion": rand_date(date(2023, 6, 1), date(2024, 12, 1))
                              if is_completed else None,
                "outcome": rng.choice(outcomes) if is_completed else None,
            })

    return student_ids


def seed_mobility(
    conn, institution_ids: list[int],
    student_ids: list[int],
    staff_ids: list[int],
    program_ids: list[int],
):
    # ~20% of students have a mobility record
    mobile_students = rng.sample(student_ids, k=int(len(student_ids) * 0.20))
    for sid in mobile_students:
        from_inst, to_inst = rng.sample(institution_ids[:6], 2)
        conn.execute(text("""
            INSERT INTO mobility_records
                (person_type, person_id, from_institution_id, to_institution_id,
                 program_id, start_date, end_date, modality)
            VALUES
                (:ptype, :pid, :from_inst, :to_inst,
                 :prog_id, :start, :end, :modality)
        """), {
            "ptype": "student", "pid": sid,
            "from_inst": from_inst, "to_inst": to_inst,
            "prog_id": rng.choice(program_ids),
            "start": rand_date(date(2023, 2, 1), date(2024, 8, 1)),
            "end": rand_date(date(2024, 8, 2), date(2024, 12, 31)),
            "modality": rng.choice(["physical", "virtual"]),
        })

    # ~30% of staff have a mobility record
    mobile_staff = rng.sample(staff_ids, k=max(1, int(len(staff_ids) * 0.30)))
    for sid in mobile_staff:
        from_inst, to_inst = rng.sample(institution_ids[:6], 2)
        conn.execute(text("""
            INSERT INTO mobility_records
                (person_type, person_id, from_institution_id, to_institution_id,
                 program_id, start_date, end_date, modality)
            VALUES
                (:ptype, :pid, :from_inst, :to_inst,
                 :prog_id, :start, :end, :modality)
        """), {
            "ptype": "staff", "pid": sid,
            "from_inst": from_inst, "to_inst": to_inst,
            "prog_id": rng.choice(program_ids),
            "start": rand_date(date(2023, 1, 1), date(2024, 6, 1)),
            "end": rand_date(date(2024, 6, 2), date(2024, 12, 31)),
            "modality": rng.choice(["physical", "virtual"]),
        })


def seed_events(
    conn, network_id: int,
    institution_ids: list[int],
):
    event_types = ["meeting", "workshop", "seminar", "review"]
    languages = ["en", "vi", "en", "en"]  # weighted toward English

    for i in range(24):   # 24 events over 2 years
        host = rng.choice(institution_ids[:5])
        event_date = rand_date(date(2023, 1, 1), date(2024, 12, 31))
        conn.execute(text("""
            INSERT INTO events
                (name, type, host_institution_id, network_id, event_date, language)
            VALUES
                (:name, :type, :host, :network_id, :event_date, :lang)
        """), {
            "name": f"VASTN {event_types[i % 4].title()} #{i+1}",
            "type": event_types[i % 4],
            "host": host,
            "network_id": network_id,
            "event_date": event_date,
            "lang": rng.choice(languages),
        })
        eid = conn.execute(
            text("SELECT MAX(event_id) FROM events")
        ).scalar()

        # 2-6 institutions participate per event
        participants = rng.sample(institution_ids, k=rng.randint(2, 6))
        for inst_id in participants:
            conn.execute(text("""
                INSERT INTO event_participants (event_id, institution_id, participant_count)
                VALUES (:eid, :inst_id, :count)
            """), {
                "eid": eid,
                "inst_id": inst_id,
                "count": rng.randint(2, 15),
            })


def seed_kpi_definitions(conn):
    kpis = [
        ("K01", "Network Participation Rate", "collaboration", "percentage",
         "Active institutions / Total member institutions", 80.0, "below"),
        ("K02", "Inter-institutional Collaboration Index", "collaboration", "percentage",
         "Unique institution pairs co-hosting >= 1 program or event / Total possible pairs",
         30.0, "below"),
        ("K03", "Student Mobility Rate", "collaboration", "percentage",
         "Students with >= 1 mobility record / Total enrolled students", 15.0, "below"),
        ("K04", "Joint Event Frequency", "collaboration", "count",
         "Events with participants from >= 2 institutions per semester", 4.0, "below"),
        ("K05", "Program Completion Rate", "academic", "percentage",
         "Enrollments with outcome pass / Total enrollments", 75.0, "below"),
        ("K06", "Student Withdrawal Rate", "academic", "percentage",
         "Enrollments with status withdrawn / Total enrollments", 10.0, "above"),
        ("K07", "Multilingual Program Coverage", "academic", "percentage",
         "Programs offering instruction in >= 2 languages / Total programs", 25.0, "below"),
        ("K08", "New Member Growth Rate", "operational", "percentage",
         "Institutions joined in period / Institutions at period start", 5.0, "below"),
        ("K09", "HITL Review Turnaround Time", "operational", "hours",
         "Average hours between AI output generated and human review completed",
         48.0, "above"),
        ("K10", "Ethics Compliance Rate", "operational", "percentage",
         "Audit log entries passing all ethics checks / Total evaluated entries",
         95.0, "below"),
    ]
    for row in kpis:
        conn.execute(text("""
            INSERT INTO kpi_definitions
                (kpi_id, name, category, unit, formula_description,
                 target_threshold, alert_direction)
            VALUES
                (:kpi_id, :name, :category, :unit, :formula_description,
                 :target_threshold, :alert_direction)
            ON CONFLICT (kpi_id) DO NOTHING
        """), {
            "kpi_id": row[0], "name": row[1], "category": row[2],
            "unit": row[3], "formula_description": row[4],
            "target_threshold": row[5], "alert_direction": row[6],
        })


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🌱 Seeding EdNet synthetic dataset...")
    with engine.begin() as conn:
        network_id = seed_network(conn)
        print(f"  ✔ Network created (id={network_id})")

        inst_ids = seed_institutions(conn, network_id)
        print(f"  ✔ {len(inst_ids)} institutions created")

        staff_ids = seed_staff(conn, inst_ids)
        print(f"  ✔ {len(staff_ids)} staff members created")

        program_ids = seed_programs(conn, network_id, inst_ids, staff_ids)
        print(f"  ✔ {len(program_ids)} programs created")

        student_ids = seed_students_and_enrollments(conn, inst_ids, program_ids)
        print(f"  ✔ {len(student_ids)} students + enrollments created")

        seed_mobility(conn, inst_ids, student_ids, staff_ids, program_ids)
        print("  ✔ Mobility records created")

        seed_events(conn, network_id, inst_ids)
        print("  ✔ Events and participants created")

        seed_kpi_definitions(conn)
        print("  ✔ KPI definitions seeded")

    print("\n✅ Dataset ready. Run the KPI engine to compute initial values:")
    print("   docker compose exec app python -c "
          "\"from modules.analytics.kpi_engine import KPIEngine; "
          "KPIEngine().compute_all()\"")


if __name__ == "__main__":
    main()