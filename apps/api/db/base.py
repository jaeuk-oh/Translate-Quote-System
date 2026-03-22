"""
SQLAlchemy Base 클래스.
모든 모델이 이 Base를 상속하여 Alembic이 마이그레이션 대상을 자동 감지.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Alembic env.py에서 자동 임포트될 수 있도록 모든 모델을 여기서 재익스포트
# (이 import 순서가 중요: Base 정의 후 모델 임포트)
from models.user import User          # noqa: F401, E402
from models.job import Job, JobEvent  # noqa: F401, E402
from models.quote import Quote        # noqa: F401, E402
from models.translator import Translator  # noqa: F401, E402
from models.assignment import Assignment  # noqa: F401, E402
from models.notification import Notification  # noqa: F401, E402
