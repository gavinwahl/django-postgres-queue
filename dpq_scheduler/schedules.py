import datetime


def combine(date, time, tzinfo):
    """
    Like datetime.datetime.combine, but works across dst transitions.
    """
    return tzinfo.localize(datetime.datetime.combine(date, time))


def repeater(delta):
    return lambda prev: prev + delta


def every_day_at(t, tz):
    def schedule(prev):
        todays_at = combine(prev.astimezone(tz).date(), t, tz)
        if prev < todays_at:
            return todays_at
        else:
            return combine(todays_at + datetime.timedelta(days=1), t, tz)
    return schedule


def every_dow_at(dow, at, tz):
    def schedule(prev):
        prev = prev.astimezone(tz)
        start_of_this_week = prev.date() - datetime.timedelta(days=prev.date().weekday())
        this_weeks_at = combine(start_of_this_week + datetime.timedelta(days=dow), at, tz)
        if prev < this_weeks_at:
            return this_weeks_at
        else:
            return combine(start_of_this_week + datetime.timedelta(days=7 + dow), at, tz)
    return schedule
