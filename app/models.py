from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(Integer, unique=True, index=True)
    amount = Column(Integer)
    description = Column(String)
    status = Column(String, default="PENDING")
    # THÊM DÒNG NÀY ĐỂ LƯU LINK
    checkout_url = Column(String) 
    created_at = Column(DateTime, default=datetime.utcnow)