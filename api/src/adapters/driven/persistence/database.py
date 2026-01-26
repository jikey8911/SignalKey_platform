from sqlalchemy import create_all, create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class VirtualBalance(Base):
    __tablename__ = 'virtual_balances'
    id = Column(Integer, primary_key=True)
    market_type = Column(String) # "CEX" or "DEX"
    asset = Column(String) # e.g., "USDT", "SOL"
    amount = Column(Float)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)

class TradeHistory(Base):
    __tablename__ = 'trade_history'
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    side = Column(String) # "BUY" or "SELL"
    price = Column(Float)
    amount = Column(Float)
    market_type = Column(String)
    is_demo = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

engine = create_engine('sqlite:///trading_bot.db')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    # Inicializar balances si no existen
    db = SessionLocal()
    if not db.query(VirtualBalance).first():
        db.add(VirtualBalance(market_type="CEX", asset="USDT", amount=10000.0))
        db.add(VirtualBalance(market_type="DEX", asset="SOL", amount=100.0))
        db.commit()
    db.close()
