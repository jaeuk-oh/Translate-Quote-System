"""
SQLAlchemy Base 클래스.
모든 모델이 이 Base를 상속하여 ORM 테이블 매핑에 사용.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
