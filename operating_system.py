import subprocess


class LinuxStandbyLock:
    COMMAND = 'systemctl'
    ARGS = ['sleep.target', 'suspend.target', 'hibernate.target', 'hybrid-sleep.target']

    @classmethod
    def inhibit(cls):
        subprocess.run([cls.COMMAND, 'mask', *cls.ARGS])

    @classmethod
    def release(cls):
        subprocess.run([cls.COMMAND, 'unmask', *cls.ARGS])



import ctypes
class WindowsStandbyLock:
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    INHIBIT = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    RELEASE = ES_CONTINUOUS

    @classmethod
    def inhibit(cls):
        ctypes.windll.kernel32.SetThreadExecutionState(cls.INHIBIT)

    @classmethod
    def release(cls):
        ctypes.windll.kernel32.SetThreadExecutionState(cls.RELEASE)
