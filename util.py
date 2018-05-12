import datetime
import re
import dateutil.parser

def date_transform(text):
    return dateutil.parser.parse(text).date()


def correct_time(string_time):
    match = re.fullmatch(r'^(([0,1][0-9])|(2[0-3])):[0-5][0-9]$', string_time)
    return bool(match)


def entered_correct(goal):
    ''' Check if entered goal matches the next format -
    *dd.mm.YYYY dd.mm.YYYY some abstract goal *
    [date of start(must be after today's date), date of finish(must be after today and date of start)]'''

    match = re.fullmatch(r'\s*\d{2}\.\d{2}\.\d{4}\s+\d{2}\.\d{2}\.\d{4}\s+\w.*',
                         goal)  # check if a format is correct: date date goal
    if not match: return False

    today = datetime.date.today()
    date_format = r'\d{2}\.\d{2}\.\d{4}'

    start = re.findall(date_format, goal)[0]  # get start date
    try:
        start = datetime.datetime.strptime(start, '%d.%m.%Y').date()  # validate start date
        if start < today:
            return False
    except ValueError:
        return False

    finish = re.findall(date_format, goal)[1]  # get finish date
    try:
        finish = datetime.datetime.strptime(finish, '%d.%m.%Y').date()  # validate finish date
        if (finish < today) | (finish < start):
            return False
    except ValueError:
        return False

    return True


def parse_goal(goal):
    '''get date of start and finish, and user's goal '''

    date_format = r'\d{2}\.\d{2}\.\d{4}'
    start, finish = re.findall(date_format, goal)[0], re.findall(date_format, goal)[1]
    start = datetime.datetime.strptime(start, '%d.%m.%Y').date()
    finish = datetime.datetime.strptime(finish, '%d.%m.%Y').date()
    goal = ' '.join(re.split(' ', goal)[2:]).strip()

    return start, finish, goal


def correct_subgoal(subgoal, goal_start, goal_finish):
    if not entered_correct(subgoal):
        return False
    sub_start, sub_finish, _ = parse_goal(subgoal)
    # must be: goal_start <= subgoal_start < subgoal_finish <= goal_start
    if (goal_start > sub_start) | (sub_start >= sub_finish) | (sub_finish > goal_finish):
        return False
    return True


def is_correct_week_reminder(rem):
    match = re.fullmatch(r'\s*(monday|sunday|tuesday|wednesday|thursday|friday|saturday)\s+(([0,1][0-9])|(2[0-3])):[0-5][0-9]+\s+\w+.*', rem)
    return bool(match)

def parse_week_reminder(rem):
    data = rem.split()
    day = data[0]
    hour = data[1]
    text_message = ' '.join(data[2:])
    return day, hour, text_message


def is_correct_day_reminder(rem):
    match = re.fullmatch(r'\s*(([0,1][0-9])|(2[0-3])):[0-5][0-9]+\s+\w+.*', rem)
    return bool(match)

def parse_day_reminder(rem):
    data = rem.split()
    hour = data[0]
    text_message = ' '.join(data[1:])
    return  hour, text_message