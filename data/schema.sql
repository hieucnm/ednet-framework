-- ── Governance ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id              VARCHAR(36) PRIMARY KEY,
    session_id          VARCHAR(36) NOT NULL,
    task_type           VARCHAR(64) NOT NULL,
    template_name       VARCHAR(64) NOT NULL,
    model_provider      VARCHAR(32),
    model_name          VARCHAR(64),
    temperature         NUMERIC(3,2),
    input_hash          VARCHAR(64),
    output_text         TEXT,
    language            VARCHAR(8),
    consequence_level   VARCHAR(16),
    all_checks_passed   BOOLEAN DEFAULT TRUE,
    failed_checks       TEXT,
    status              VARCHAR(32) DEFAULT 'DELIVERED',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitl_reviews (
    review_id           VARCHAR(64) PRIMARY KEY,
    log_id              VARCHAR(36) REFERENCES audit_logs(log_id),
    reviewer_id         VARCHAR(64),
    decision            VARCHAR(16) CHECK (decision IN ('approved','edited','rejected')),
    edited_output       TEXT,
    review_note         TEXT,
    reviewed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_status
    ON audit_logs(status);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
    ON audit_logs(created_at);

-- ── Networks & Institutions ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS networks (
    network_id          SERIAL PRIMARY KEY,
    name                VARCHAR(256) NOT NULL,
    type                VARCHAR(64),
    established_date    DATE,
    description         TEXT
);

CREATE TABLE IF NOT EXISTS institutions (
    institution_id      SERIAL PRIMARY KEY,
    name                VARCHAR(256) NOT NULL,
    country             VARCHAR(64),
    type                VARCHAR(64),
    joined_date         DATE
);

CREATE TABLE IF NOT EXISTS network_memberships (
    network_id          INT REFERENCES networks(network_id),
    institution_id      INT REFERENCES institutions(institution_id),
    role                VARCHAR(64),
    since_date          DATE,
    PRIMARY KEY (network_id, institution_id)
);

-- ── Programs & Courses ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS programs (
    program_id          SERIAL PRIMARY KEY,
    name                VARCHAR(256) NOT NULL,
    host_institution_id INT REFERENCES institutions(institution_id),
    network_id          INT REFERENCES networks(network_id),
    start_date          DATE,
    end_date            DATE,
    field               VARCHAR(128),
    language            VARCHAR(8),
    status              VARCHAR(32) DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS program_partners (
    program_id          INT REFERENCES programs(program_id),
    institution_id      INT REFERENCES institutions(institution_id),
    role                VARCHAR(64),
    PRIMARY KEY (program_id, institution_id)
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id            SERIAL PRIMARY KEY,
    institution_id      INT REFERENCES institutions(institution_id),
    name                VARCHAR(128),
    role                VARCHAR(64),
    email               VARCHAR(128)
);

CREATE TABLE IF NOT EXISTS courses (
    course_id           SERIAL PRIMARY KEY,
    program_id          INT REFERENCES programs(program_id),
    name                VARCHAR(256),
    credits             INT,
    language            VARCHAR(8),
    modality            VARCHAR(32),
    instructor_id       INT REFERENCES staff(staff_id)
);

-- ── Students & Mobility ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS students (
    student_id          SERIAL PRIMARY KEY,
    home_institution_id INT REFERENCES institutions(institution_id),
    name                VARCHAR(128),
    enrollment_year     INT,
    field_of_study      VARCHAR(128)
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id       SERIAL PRIMARY KEY,
    student_id          INT REFERENCES students(student_id),
    program_id          INT REFERENCES programs(program_id),
    enrolled_date       DATE,
    status              VARCHAR(32) DEFAULT 'ongoing',
    completion_date     DATE,
    outcome             VARCHAR(32)
);

CREATE TABLE IF NOT EXISTS mobility_records (
    mobility_id         SERIAL PRIMARY KEY,
    person_type         VARCHAR(16),
    person_id           INT,
    from_institution_id INT REFERENCES institutions(institution_id),
    to_institution_id   INT REFERENCES institutions(institution_id),
    program_id          INT REFERENCES programs(program_id),
    start_date          DATE,
    end_date            DATE,
    modality            VARCHAR(32)
);

-- ── Events ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    event_id            SERIAL PRIMARY KEY,
    name                VARCHAR(256),
    type                VARCHAR(64),
    host_institution_id INT REFERENCES institutions(institution_id),
    network_id          INT REFERENCES networks(network_id),
    event_date          DATE,
    language            VARCHAR(8)
);

CREATE TABLE IF NOT EXISTS event_participants (
    event_id            INT REFERENCES events(event_id),
    institution_id      INT REFERENCES institutions(institution_id),
    participant_count   INT DEFAULT 0,
    PRIMARY KEY (event_id, institution_id)
);

-- ── KPI Store ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS kpi_definitions (
    kpi_id              VARCHAR(8) PRIMARY KEY,
    name                VARCHAR(128),
    category            VARCHAR(64),
    unit                VARCHAR(32),
    formula_description TEXT,
    target_threshold    NUMERIC(10,4),
    alert_direction     VARCHAR(8)
);

CREATE TABLE IF NOT EXISTS kpi_values (
    value_id            SERIAL PRIMARY KEY,
    kpi_id              VARCHAR(8) REFERENCES kpi_definitions(kpi_id),
    scope_type          VARCHAR(32),
    scope_id            INT,
    period_start        DATE,
    period_end          DATE,
    value               NUMERIC(10,4),
    computed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kpi_values_kpi_period
    ON kpi_values(kpi_id, period_start, period_end);

CREATE INDEX IF NOT EXISTS idx_kpi_values_scope
    ON kpi_values(scope_type, scope_id);
