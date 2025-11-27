"""SQLAlchemy Baseクラス定義.

全てのモデルクラスが継承するベースクラスを定義します。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy ORMのベースクラス."""

