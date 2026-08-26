from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


# A NAT or pooler between the app and a remote Postgres can drop idle TCP
# connections silently (no RST); a dead pooled socket then hangs even
# pool_pre_ping's SELECT 1 until the kernel's retransmission timeout.
# Keepalives surface the break within ~60s and pool_recycle retires
# connections before they can go stale in the first place.
KEEPALIVE_CONNECT_ARGS = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "connect_timeout": 10,
}

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_recycle=240,
    connect_args=KEEPALIVE_CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
