import unittest

from numpy import testing

# Upper bound, in seconds, for a run that was given a time limit of a
# millisecond or so. The tests using it check that such a run returns promptly
# and with the right answer rather than running away.
#
# It is deliberately far larger than the limit itself. The bound used to be two
# milliseconds, which left about a millisecond of slack for the whole round
# trip through the extension module and for the operating system to schedule
# the process. That held on the development machine and failed on a Windows
# runner, where the default timer granularity is around 15 milliseconds: the
# assertion was measuring the machine rather than the library.
TIME_LIMIT_TOLERANCE = 1.0


class TestingBase(unittest.TestCase):
    def check_result(self, alg, path, cost, resources, almost=False) -> bool:
        self.assertEqual(alg.path, path)
        if almost:
            self.assertAlmostEqual(alg.total_cost, cost, places=2)
        else:
            self.assertEqual(alg.total_cost, cost)
        self.assertIsNone(testing.assert_allclose(alg.consumed_resources, resources))
