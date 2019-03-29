import datetime
import pytz

from django.test import SimpleTestCase

from .schedules import repeater, every_day_at, every_dow_at


DENVER = pytz.timezone('America/Denver')


def tztime(tz, *args, **kwargs):
    if not isinstance(tz, datetime.tzinfo):
        tz = pytz.timezone(tz)
    naive = datetime.datetime(*args, **kwargs)
    return tz.localize(naive)


class TestSchedulers(SimpleTestCase):
    def test_repeater(self):
        now = tztime('UTC', 2019, 1, 1, 0, 0, 0)
        n = repeater(datetime.timedelta(seconds=5))(now)
        self.assertEqual(n, tztime('UTC', 2019, 1, 1, 0, 0, 5))

    def test_every_day_at_before(self):
        now = tztime('UTC', 2019, 1, 1, 0, 0, 0)
        n = every_day_at(datetime.time(8), pytz.UTC)(now)
        self.assertEqual(n, tztime('UTC', 2019, 1, 1, 8))

    def test_every_day_at_after(self):
        now = tztime('UTC', 2019, 1, 1, 9, 0, 0)
        n = every_day_at(datetime.time(8), pytz.UTC)(now)
        self.assertEqual(n, tztime('UTC', 2019, 1, 2, 8))

    def test_every_day_dst_transition(self):
        now = tztime(DENVER, 2019, 11, 2, 8, 0, 0)
        n = every_day_at(datetime.time(8), DENVER)(now)
        self.assertEqual(n, tztime(DENVER, 2019, 11, 3, 8))

    def test_every_day_different_time_zones(self):
        now = tztime('UTC', 2019, 11, 3, 0, 0, 0)
        n = every_day_at(datetime.time(22), pytz.FixedOffset(-180))(now)
        self.assertEqual(n, tztime(pytz.FixedOffset(-180), 2019, 11, 2, 22))

    def test_every_dow_at_before(self):
        now = tztime(DENVER, 2019, 11, 2, 8, 0, 0)
        n = every_dow_at(6, datetime.time(8), DENVER)(now)
        self.assertEqual(n, tztime(DENVER, 2019, 11, 3, 8))

    def test_every_dow_at_after(self):
        now = tztime(DENVER, 2019, 11, 3, 8, 0, 0)
        n = every_dow_at(2, datetime.time(8), DENVER)(now)
        self.assertEqual(n, tztime(DENVER, 2019, 11, 6, 8))

    def test_every_dow_equal(self):
        now = tztime(DENVER, 2019, 11, 3, 8, 0, 0)
        n = every_dow_at(6, datetime.time(8), DENVER)(now)
        self.assertEqual(n, tztime(DENVER, 2019, 11, 10, 8))

    def test_every_dow_different_time_zones(self):
        now = tztime('UTC', 2019, 11, 4, 0, 0, 0)
        n = every_dow_at(6, datetime.time(22), pytz.FixedOffset(-180))(now)
        self.assertEqual(n, tztime(pytz.FixedOffset(-180), 2019, 11, 3, 22))
