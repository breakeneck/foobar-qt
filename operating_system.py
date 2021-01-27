class LinuxStandbyLock:
    COMMAND = 'systemctl'
    ARGS = ['sleep.target', 'suspend.target', 'hibernate.target', 'hybrid-sleep.target']

    @classmethod
    def inhibit(cls):
        import subprocess
        subprocess.run([cls.COMMAND, 'mask', *cls.ARGS])

    @classmethod
    def release(cls):
        import subprocess
        subprocess.run([cls.COMMAND, 'unmask', *cls.ARGS])


class WindowsStandbyLock:
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    INHIBIT = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    RELEASE = ES_CONTINUOUS

    @classmethod
    def inhibit(cls):
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(cls.INHIBIT)

    @classmethod
    def release(cls):
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(cls.RELEASE)
