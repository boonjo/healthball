from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Player(Base):
    __tablename__ = "players"

    player_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    dob = Column(Date)
    position = Column(String)

    injuries = relationship("Injury", back_populates="player")


class Injury(Base):
    __tablename__ = "injuries"

    injury_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.player_id"))
    injury_type = Column(String)
    days_out = Column(Integer)
    age_at_injury = Column(Integer)
    minutes_before = Column(Integer)
    minutes_total = Column(Integer)

    player = relationship("Player", back_populates="injuries")
