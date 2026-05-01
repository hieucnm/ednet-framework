# modules/analytics/db_connector.py

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL environment variable is not set.")
        _engine = create_engine(database_url, pool_pre_ping=True)
    return _engine


@contextmanager
def get_session():
    Session = sessionmaker(bind=get_engine())
    session = Session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()