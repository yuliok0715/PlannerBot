import config
import telebot
from models import Base
from models import User, Goal, Subgoal, Reminder
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from util import date_transform, entered_correct, parse_goal, correct_subgoal, correct_time, is_correct_day_reminder,\
    is_correct_week_reminder, parse_day_reminder, parse_week_reminder
import schedule
import time
from multiprocessing import Process
from functools import partial
import datetime


bot = telebot.TeleBot(config.TOKEN)
engine = sa.create_engine(config.DATABASE_URL, echo=True)
Session = sessionmaker(bind=engine)


@bot.message_handler(commands=['start'])
def init(message):
    user_name = message.from_user.first_name
    session = Session()
    user = User(chat_id=message.chat.id, name=user_name)
    session.add(user)
    session.commit()
    session.close()
    bot.send_message(message.chat.id, f"{user_name}, welcome to our planner!")
    help(message)


@bot.message_handler(commands=['help'])
def help(message):
    help_msg = open('help.txt').read()
    bot.send_message(message.chat.id, help_msg)


@bot.message_handler(commands=['add_goal'])
def add_goal(message):
    text_splits = message.text.split(maxsplit=1)
    goal_main = text_splits[1]
    if entered_correct(goal_main):
        goal_created, goal_deadline, goal_name = parse_goal(goal_main)
        session = Session()
        goal = Goal(chat_id=message.chat.id, name=goal_name, deadline = goal_deadline,
                    created=goal_created, flag_finished=False)
        session.add(goal)
        session.commit()
        text = "List of your goals: \n"
        for goal in session.query(Goal).filter(Goal.chat_id == message.chat.id):
            text += goal.name + '\n'
        session.close()
        bot.send_message(message.chat.id, text)
    else:
        bot.send_message(message.chat.id, "Sorry, your data isn't correct")


@bot.message_handler(commands=['add_reminder'])
def add_reminder_command(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have to create goal before adding reminder')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose goal to add reminder", reply_markup=markup)
        bot.register_next_step_handler(msg, add_reminder_middle)
    session.close()


def add_reminder_middle(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in goal.subgoal if not goal.flag_finished]
    if not data:
        bot.send_message(message.chat.id,
                         'Sorry, you should to add subgoal before adding reminder, cause in our planner reminders avaiable only for subgoals')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose subgoal to add reminder", reply_markup=markup)
        bot.register_next_step_handler(msg, add_reminder_part)
    session.close()


def add_reminder_part(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
    session.close()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = ['1+ times per day', '1+ times per week']
    markup.add(*data)
    msg = bot.send_message(message.chat.id, "Choose frequency", reply_markup=markup)
    bot.register_next_step_handler(msg, partial(choose_frequency, subgoal=goal))


@bot.message_handler(commands=['add_subgoal'])
def add_subgoal(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you should to add goal before adding subgoal')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your goal", reply_markup=markup)
        bot.register_next_step_handler(msg, switched)
    session.close()


def switched(message):
    msg = bot.send_message(message.chat.id, f"Please reply to this message with params of subgoal that you want to add for {message.text}")
    bot.register_for_reply(msg, add_subgoal_body)


def add_subgoal_body(message):
    session = Session()
    original = message.reply_to_message
    name_of_owner_goal = original.text[77:]
    goal_owner = session.query(Goal).filter(Goal.name == name_of_owner_goal)[0]
    goal_id_new = goal_owner.goal_id
    start = goal_owner.created
    finish = goal_owner.deadline
    if correct_subgoal(message.text, start, finish):
        goal_created, goal_deadline, goal_name = parse_goal(message.text)

        goal = Subgoal(goal_id=goal_id_new, name=goal_name, deadline=goal_deadline,
                    created=goal_created, flag_finished=False)
        session.add(goal)
        session.commit()
        text = "List of your subgoals for this goal: \n"
        for goal in session.query(Subgoal).filter(Subgoal.goal_id == goal_id_new):
            text += goal.name + '\n'
        bot.send_message(message.chat.id, text)
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        data = ['1+ times per day', '1+ times per week']
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose frequency", reply_markup=markup)
        bot.register_next_step_handler(msg, partial(choose_frequency, subgoal=goal))
    else:
        bot.send_message(message.chat.id, "Sorry, your data isn't correct")
        msg = bot.send_message(message.chat.id,
                               f"Please reply to this message with params of subgoal that you want to add for {name_of_owner_goal}")
        bot.register_for_reply(msg, add_subgoal_body)


def choose_frequency(message, subgoal):
    if message.text == '1+ times per day':
        msg = bot.send_message(message.chat.id, 'Ok, how many times per day do you want to get notification? Reply to this message')
        bot.register_for_reply(msg, partial(get_frequency, freq='day', subgoal=subgoal, exc_msg=message))
    if message.text == '1+ times per week':
        msg = bot.send_message(message.chat.id,'Ok, how many times per week do you want to get notification? Reply to this message')
        bot.register_for_reply(msg, partial(get_frequency, freq='week', subgoal=subgoal, exc_msg=message))


def get_frequency(message, freq, subgoal, exc_msg):
    try:
        frequency = int(message.text)
    except:
        bot.send_message(message.chat.id, 'Sorry, incorrect input')
        choose_frequency(exc_msg, subgoal)
    else:
        for i in range(frequency):
            add_reminder(subgoal, message.chat.id, i+1, frequency, freq)


def add_reminder(goal, chat_id, time, freq, day_week):
    if day_week == 'week':
        msg = bot.send_message(chat_id, f"Now you should add {time} of {freq} notification for subgoal {goal.name}. Please, reply to this message in format day_of_week hh:mm text_of_notification ")
    if day_week == 'day':
        msg = bot.send_message(chat_id, f"Now you should add {time} of {freq} notification for subgoal {goal.name}. Please, reply to this message in format hh:mm text_of_notification ")
    bot.register_for_reply(msg, partial(add_reminder_body, goal=goal, freq=day_week, t=time, f=freq))


def add_reminder_body(message, goal, freq, t, f):
    time = ''
    text = ''
    dayofweek=''
    if freq == 'week':
        if is_correct_week_reminder(message.text):
            dayofweek, time, text = parse_week_reminder(message.text)
        else:
            add_reminder(goal, message.chat.id, t, f, freq )
    if freq == 'day':
        dayofweek = 'all'
        if is_correct_day_reminder(message.text):
            time, text = parse_day_reminder(message.text)
        else:
            add_reminder(goal, message.chat.id, t, f, freq)
    if time and text and dayofweek:
        session = Session()
        reminder = Reminder(subgoal_id=goal.subgoal_id, dayofweek=dayofweek, start=time,
                            text=text, chat_id=message.chat.id, flag_set=False, flag_delete=False, flag_once=False)
        session.add(reminder)
        session.commit()
        session.close()
        bot.send_message(message.chat.id, "Reminder successfully added!")


@bot.message_handler(commands=['goal_done'])
def goal_done(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not unfinished goals')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose goal that you have done", reply_markup=markup)
        bot.register_next_step_handler(msg, goal_done_body)
    session.close()


def goal_done_body(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    goal.flag_finished = True
    session.commit()
    for subgoal in goal.subgoal:
        subgoal.flag_finished=True
        for reminder in session.query(Reminder).filter(Reminder.subgoal_id == subgoal.subgoal_id):
            reminder.flag_delete = True
            session.commit()
        session.commit()
    today = datetime.date.today()
    if goal.deadline > today:
        bot.send_message(message.chat.id, f"Woooow, you did it {(goal.deadline - today).days} days earlier than you had planned")
    if goal.deadline < today:
        bot.send_message(message.chat.id, f"You did it {(today - goal.deadline).days} days later than you had planned")
    if goal.deadline == today:
        bot.send_message(message.chat.id, "Wow. You are like swiss watches")


@bot.message_handler(commands=['subgoal_done'])
def subgoal_done(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not unfinished goals')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose main goal for subgoal that you have done", reply_markup=markup)
        bot.register_next_step_handler(msg, subgoal_done_middle)
    session.close()


def subgoal_done_middle(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in goal.subgoal if not goal.flag_finished]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not unfinished subgoals for this goal')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose subgoal that you have finished", reply_markup=markup)
        bot.register_next_step_handler(msg, subgoal_done_body)
    session.close()


def subgoal_done_body(message):
    goal_name = message.text
    session = Session()
    subgoal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
    subgoal.flag_finished = True
    session.commit()
    for reminder in session.query(Reminder).filter(Reminder.subgoal_id == subgoal.subgoal_id):
        reminder.flag_delete = True
        session.commit()
    today = datetime.date.today()
    if subgoal.deadline > today:
        bot.send_message(message.chat.id,
                         f"Woooow, you did it {(subgoal.deadline - today).days} days earlier than you had planned")
    if subgoal.deadline < today:
        bot.send_message(message.chat.id, f"You did it {(today - subgoal.deadline).days} days later than you had planned")
    if subgoal.deadline == today:
        bot.send_message(message.chat.id, "Wow. You are like swiss watches")


@bot.message_handler(commands=['delete_goal'])
def delete_goal(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not goals to delete')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your goal to delete", reply_markup=markup)
        bot.register_next_step_handler(msg, delete_goal_body)
    session.close()


def delete_goal_body(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    id = goal.goal_id
    session.delete(goal)
    session.commit()
    for subgoal in session.query(Subgoal).filter(Subgoal.goal_id == id):
        subgoal_id = subgoal.subgoal_id
        session.delete(subgoal)
        session.commit()
        for reminder in session.query(Reminder).filter(Reminder.subgoal_id == subgoal_id):
            reminder.flag_delete = True
            session.commit()
    bot.send_message(message.chat.id, "Deleted")
    if not len(session.query(Goal).filter(Goal.chat_id == message.chat.id)):
        text = 'You have not goals :)'
    else:
        text = "List of your goals: \n"
    for goal in session.query(Goal).filter(Goal.chat_id == message.chat.id):
        text += goal.name + '\n'
    session.close()
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['delete_subgoal'])
def delete_subgoal(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not subgoals to delete')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose main goal of subgoal to delete", reply_markup=markup)
        bot.register_next_step_handler(msg, delete_subgoal_middle)
    session.close()


def delete_subgoal_middle(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in goal.subgoal]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not subgoals to delete')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose subgoal to delete", reply_markup=markup)
        bot.register_next_step_handler(msg, delete_subgoal_body)
    session.close()


def delete_subgoal_body(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
    goal_id = goal.goal_id
    subgoal_id = goal.subgoal_id
    session.delete(goal)
    session.commit()
    for reminder in session.query(Reminder).filter(Reminder.subgoal_id==subgoal_id):
        reminder.flag_delete = True
        session.commit()
    bot.send_message(message.chat.id, "Deleted")
    goal_owner = session.query(Goal).filter(Goal.goal_id == goal_id)[0]
    if not goal_owner.subgoal:
        text = f'You have not subgoals for {goal_owner.name}'
    else:
        text = f"List of your subgoals for {goal_owner.name}: \n"
    for goal in goal_owner.subgoal:
        text += goal.name + '\n'
    session.close()
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['edit_goal'])
def edit_goal(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you should add goal before editing')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your goal to edit", reply_markup=markup)
        bot.register_next_step_handler(msg, edit_goal_part)
    session.close()


@bot.message_handler(commands=['edit_subgoal'])
def edit_goal(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in session.query(Goal).filter_by(chat_id=message.chat.id, flag_finished=False)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you should add goal before editing some subgoal')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your main goal for subgoal to edit", reply_markup=markup)
        bot.register_next_step_handler(msg, edit_subgoal_part)
    session.close()


def edit_subgoal_part(message):
    goal_name = message.text
    session = Session()
    goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [goal.name for goal in goal.subgoal]
    if not data:
        bot.send_message(message.chat.id, f'Sorry, you should add subgoal to main goal {goal.name} before editing')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose subgoal to edit", reply_markup=markup)
        bot.register_next_step_handler(msg, edit_subgoal_middle)
    session.close()


def edit_subgoal_middle(message):
    session = Session()
    goal_name = message.text
    session.close()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = ['name', 'start', 'deadline']
    markup.add(*data)
    msg = bot.send_message(message.chat.id, "What do you want to edit?", reply_markup=markup)
    bot.register_next_step_handler(msg, partial(edit_goal_body, goal_name=goal_name, subgoal=True))

def edit_goal_part(message):
    goal_name = message.text
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = ['name', 'start', 'deadline']
    markup.add(*data)
    msg = bot.send_message(message.chat.id, "What do you want to edit?", reply_markup=markup)
    bot.register_next_step_handler(msg, partial(edit_goal_body, goal_name=goal_name, subgoal=False))


def edit_goal_body(message, goal_name, subgoal):
    what_to_edit = message.text
    if what_to_edit=='name':
        edit_name(goal_name, message.chat.id, subgoal)
    if what_to_edit=='start':
        edit_start(goal_name, message.chat.id, subgoal)
    if what_to_edit == 'deadline':
        edit_deadline(goal_name, message.chat.id, subgoal)


def edit_name(goal_name, chat_id, subgoal):
    msg = bot.send_message(chat_id, f'Reply to this message with new name of {goal_name}')
    bot.register_for_reply(msg, partial(edit_name_body, goal_name=goal_name, subgoal=subgoal))


def edit_name_body(message, goal_name, subgoal):
    new_name = message.text
    session = Session()
    if not subgoal:
        goal = session.query(Goal).filter(Goal.name == goal_name)[0]
    else:
        goal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
    goal.name = new_name
    session.commit()
    bot.send_message(message.chat.id, f"New info about this goal:\n{str(goal)}")
    session.close()


def edit_start(goal_name, chat_id, subgoal):
    msg = bot.send_message(chat_id, f'Reply to this message with new start date of {goal_name} in format dd.mm.yyyy')
    bot.register_for_reply(msg, partial(edit_start_body, goal_name=goal_name, subgoal=subgoal))


def edit_start_body(message, goal_name, subgoal):
    new_date = message.text
    try:
        new_start = date_transform(new_date)
    except:
        bot.send_message(message.chat.id, 'Sorry, incorrect input')
        edit_start(goal_name, message.chat.id, subgoal)
    else:
        session = Session()
        if not subgoal:
            goal = session.query(Goal).filter(Goal.name == goal_name)[0]
        else:
            goal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
        if new_start >= datetime.datetime.today().date() and new_start < goal.deadline:
            goal.created = new_start
            session.commit()
            bot.send_message(message.chat.id, f"New info about this goal:\n{str(goal)}")
        else:
            bot.send_message(message.chat.id, 'Sorry, incorrect input')
            edit_start(goal_name, message.chat.id, subgoal)
        session.close()


def edit_deadline(goal_name, chat_id, subgoal):
    msg = bot.send_message(chat_id, f'Reply to this message with new deadline date of {goal_name} in format dd.mm.yyyy')
    bot.register_for_reply(msg, partial(edit_deadline_body, goal_name=goal_name, subgoal=subgoal))


def edit_deadline_body(message, goal_name, subgoal):
    new_date = message.text
    try:
        new_finish = date_transform(new_date)
    except:
        bot.send_message(message.chat.id, 'Sorry, incorrect input')
        edit_deadline(goal_name, message.chat.id, subgoal)
    else:
        session = Session()
        if not subgoal:
            goal = session.query(Goal).filter(Goal.name == goal_name)[0]
        else:
            goal = session.query(Subgoal).filter(Subgoal.name == goal_name)[0]
        if new_finish >= datetime.datetime.today().date() and new_finish > goal.created:
            goal.deadline = new_finish
            session.commit()
            bot.send_message(message.chat.id, f"New info about this goal:\n{str(goal)}")
        else:
            bot.send_message(message.chat.id, 'Sorry, incorrect input')
            edit_deadline(goal_name, message.chat.id, subgoal)
        session.close()


def send_notification(reminder):
    bot.send_message(reminder.chat_id, reminder.text)
    if reminder.flag_once:
        session = Session()
        reminder.flag_delete = True
        session.commit()
        session.close()
    #msg = bot.send_message(reminder.chat_id, "If you want to delay this notification, please reply to this message with n minutes of waiting (n < 60, don't be lazy!)")
    #bot.register_for_reply(msg, partial(delay_notification, reminder=reminder))
    #markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    #data = ['15', '20', '30', '1']
    #markup.add(*data)
    #msg = bot.send_message(reminder.chat_id, "Choose your goal", reply_markup=markup)
    #bot.register_next_step_handler(msg, partial(delay_notification, reminder))


@bot.message_handler(commands=['about'])
def about_bot(message):
    text = """Do you want to plan your life? """
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['progress'])
def about_bot(message):
    session = Session()
    user = session.query(User).filter(User.chat_id==message.chat.id)[0]
    text = ''
    for goal in user.goal:
        if goal.flag_finished:
            text += goal.name + ' ✅\n'
        else:
            text += f'{goal.name}: {(goal.deadline - datetime.datetime.today().date()).days} days to go.\n Subgoals:\n'
            for subgoal in session.query(Subgoal).filter(Subgoal.goal_id == goal.goal_id):
                if subgoal.flag_finished:
                    text += subgoal.name + ' ✅\n'
                else:
                    text += f'{subgoal.name}: {(subgoal.deadline - datetime.datetime.today().date()).days} days to go\n'
        text += '\n'
    if not text:
        text = 'You have not active goals'
    bot.send_message(message.chat.id, text)
    session.close()


@bot.message_handler(commands=['delete_reminder'])
def delete_reminder(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [str(reminder) for reminder in session.query(Reminder).filter_by(chat_id=message.chat.id)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you have not active reminders')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your reminder to delete", reply_markup=markup)
        bot.register_next_step_handler(msg, delete_reminder_body)
    session.close()


def delete_reminder_body(message):
    reminder_id = int(message.text.split()[-1])
    session = Session()
    reminder = session.query(Reminder).filter(Reminder.reminder_id == reminder_id)[0]
    reminder.flag_delete = True
    session.commit()
    bot.send_message(message.chat.id, "Deleted")
    session.close()


@bot.message_handler(commands=['all_reminders'])
def all_reminders(message):
    session = Session()
    try:
        a = session.query(Reminder).filter(Reminder.chat_id == message.chat.id)[0]
    except:
        text = 'You have not active reminders'
    else:
        text = "List of your reminders: \n"
    for reminder in session.query(Reminder).filter(Reminder.chat_id == message.chat.id):
        text += str(reminder) + '\n'
    session.close()
    bot.send_message(message.chat.id, text)


@bot.message_handler(commands=['edit_reminder'])
def edit_reminder(message):
    session = Session()
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = [str(reminder) for reminder in session.query(Reminder).filter_by(chat_id=message.chat.id)]
    if not data:
        bot.send_message(message.chat.id, 'Sorry, you should add reminder before editing')
    else:
        markup.add(*data)
        msg = bot.send_message(message.chat.id, "Choose your reminder to edit", reply_markup=markup)
        bot.register_next_step_handler(msg, edit_reminder_middle)
    session.close()


def edit_reminder_middle(message):
    reminder_id = int(message.text.split()[-1])
    markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    data = ['day of week(or day on week)', 'time', 'text']
    markup.add(*data)
    msg = bot.send_message(message.chat.id, "What do you want to edit in reminder", reply_markup=markup)
    bot.register_next_step_handler(msg, partial(edit_reminder_body_part, reminder_id=reminder_id))


def edit_reminder_body_part(message, reminder_id):
    if message.text == 'day of week(or day on week)':
        edit_dayofweek(message.chat.id, reminder_id)
    if message.text == 'time':
        edit_time(message.chat.id, reminder_id)
    if message.text == 'text':
        edit_text(message.chat.id, reminder_id)

def edit_dayofweek(chat_id, reminder_id):
    msg = bot.send_message(chat_id, "If you want to make this reminder daily - reply \'all\'. In another case, reply day of week.")
    bot.register_for_reply(msg, partial(edit_dayofweek_body, reminder_id=reminder_id))


def edit_dayofweek_body(message, reminder_id):
    session = Session()
    new_day_of_week = message.text
    days = ['monday', 'tuesday', 'wednesday','thursday', 'friday', 'saturday', 'sunday', 'all']
    if new_day_of_week not in days:
        bot.send_message(message.chat.id, 'Sorry, incorrect input')
        edit_dayofweek(message.chat.id, reminder_id)
    else:
        reminder = session.query(Reminder).filter(Reminder.reminder_id == reminder_id)[0]
        reminder.flag_delete = True
        session.commit()
        reminder_new = Reminder(subgoal_id=reminder.subgoal_id, dayofweek=new_day_of_week, start=reminder.start,
                        text=reminder.text, chat_id=message.chat.id, flag_set=False, flag_delete=False, flag_once=False)
        session.add(reminder_new)
        session.commit()
        bot.send_message(message.chat.id, f"New reminder: {str(reminder_new)}")
    session.close()


def edit_time(chat_id, reminder_id):
    msg = bot.send_message(chat_id,
                           "Please, reply to this message with new time of this notification in format hh:mm")
    bot.register_for_reply(msg, partial(edit_time_body, reminder_id=reminder_id))


def edit_time_body(message, reminder_id):
    session = Session()
    new_time = message.text
    if not correct_time(new_time):
        bot.send_message(message.chat.id, 'Sorry, time must be in format hh:mm')
        edit_time(message.chat.id, reminder_id)
    else:
        reminder = session.query(Reminder).filter(Reminder.reminder_id == reminder_id)[0]
        reminder.flag_delete = True
        session.commit()
        reminder_new = Reminder(subgoal_id=reminder.subgoal_id, dayofweek=reminder.dayofweek, start=new_time,
                                    text=reminder.text, chat_id=message.chat.id, flag_set=False, flag_delete=False,
                                    flag_once=False)
        session.add(reminder_new)
        session.commit()
        bot.send_message(message.chat.id, f"New reminder: {str(reminder_new)}")
    session.close()


def edit_text(chat_id, reminder_id):
    msg = bot.send_message(chat_id,
                           "Please, reply to this message with new text for this reminder")
    bot.register_for_reply(msg, partial(edit_text_body, reminder_id=reminder_id))


def edit_text_body(message, reminder_id):
    session = Session()
    new_text = message.text
    reminder = session.query(Reminder).filter(Reminder.reminder_id == reminder_id)[0]
    reminder.text = new_text
    session.commit()
    bot.send_message(message.chat.id, f"New reminder: {str(reminder)}")
    session.close()

def scheduling():
    session = Session()
    while True:
        for reminder in session.query(Reminder).filter(Reminder.flag_delete == True):
            schedule.clear(str(reminder.reminder_id))
            session.delete(reminder)
            session.commit()
        for reminder in session.query(Reminder).filter(Reminder.flag_set==False):
            dayofweek = reminder.dayofweek
            time_start = reminder.start
            if dayofweek == 'monday':
                schedule.every().monday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'tuesday':
                schedule.every().tuesday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'wednesday':
                schedule.every().wednesday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'thursday':
                schedule.every().thursday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'friday':
                schedule.every().friday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'saturday':
                schedule.every().saturday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'sunday':
                schedule.every().sunday.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            elif dayofweek == 'all':
                schedule.every().day.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            if reminder.flag_once:
                schedule.every().day.at(time_start).do(send_notification, reminder).tag(str(reminder.reminder_id))
            reminder.flag_set = True
            session.commit()
        schedule.run_pending()
        time.sleep(10)
    session.close()

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    process_of_scheduling = Process(target=scheduling, args=())
    process_of_scheduling.start()
    bot.polling(none_stop=True)


