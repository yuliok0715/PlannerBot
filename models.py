from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    chat_id = Column(Integer, primary_key=True)
    name = Column(String)
    goal = relationship('Goal', back_populates='user_owner')
    reminder = relationship('Reminder')

    def __repr__(self):
        return f"User: chat id: {self.chat_id}, name: {self.name}, {self.goal}"


class Goal(Base):
    __tablename__ = 'goal'

    chat_id = Column(Integer, ForeignKey('user.chat_id'))
    goal_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    created = Column(Date)
    deadline = Column(Date)
    flag_finished = Column(Boolean)
    user_owner = relationship('User', back_populates='goal')
    subgoal = relationship('Subgoal')

    def __repr__(self):
        return f"Name: {self.name}\ndates: {self.created} - {self.deadline}"


class Subgoal(Base):
    __tablename__ = 'subgoal'


    subgoal_id = Column(Integer, primary_key=True)
    goal_id = Column(Integer, ForeignKey('goal.goal_id'))
    name = Column(String)
    created = Column(Date)
    deadline = Column(Date)
    flag_finished = Column(Boolean)


    def __repr__(self):
        return f"Name: {self.name}\ndates: {self.created} - {self.deadline}"


class Reminder(Base):
    __tablename__ = 'reminder'

    reminder_id = Column(Integer, primary_key=True)
    subgoal_id = Column(Integer, ForeignKey('subgoal.subgoal_id'))
    chat_id = Column(Integer, ForeignKey('user.chat_id'))
    text = Column(String)
    dayofweek = Column(String)
    start = Column(String)
    flag_set = Column(Boolean)
    flag_delete = Column(Boolean)
    flag_once = Column(Boolean)

    def __repr__(self):
        every = self.dayofweek if self.dayofweek != 'all' else 'day'
        return f"Reminder {self.text}, every {every} at {self.start}. ID: {self.reminder_id}"