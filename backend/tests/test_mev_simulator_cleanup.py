import subprocess

import pytest

from victor_ai_bot.aqe.mev.simulator import AnvilForkExecutor, ForkSimulationUnavailable


class _CleanupProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def poll(self):
        return None if not self.killed else None

    def wait(self, *, timeout):
        self.wait_calls += 1
        raise subprocess.TimeoutExpired(cmd='anvil', timeout=timeout)


def test_anvil_cleanup_kills_and_fails_closed_if_forced_wait_times_out():
    process = _CleanupProcess()

    with pytest.raises(ForkSimulationUnavailable, match='anvil_process_cleanup_timeout'):
        AnvilForkExecutor._cleanup_process(process)

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_calls == 2
