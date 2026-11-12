import threading
import unittest
from types import SimpleNamespace
from desktop import request_close


class DesktopLifecycleTests(unittest.TestCase):
    def server(self,**changes):
        values=dict(LOCK=threading.RLock(),PICKER_LOCK=threading.Lock(),BUSY=False,
                    SCANNING=False,GENERATION=SimpleNamespace(busy=lambda:False),SHUTTING_DOWN=False)
        values.update(changes)
        return SimpleNamespace(**values)

    def test_idle_close_prevents_new_tasks(self):
        server=self.server()
        self.assertEqual(request_close(server),'')
        self.assertTrue(server.SHUTTING_DOWN)

    def test_tasks_prevent_close(self):
        for changes in [dict(BUSY=True),dict(SCANNING=True),dict(GENERATION=SimpleNamespace(busy=lambda:True))]:
            server=self.server(**changes)
            self.assertTrue(request_close(server))
            self.assertFalse(server.SHUTTING_DOWN)

    def test_open_picker_prevents_close(self):
        server=self.server()
        server.PICKER_LOCK.acquire()
        self.assertTrue(request_close(server))
        self.assertFalse(server.SHUTTING_DOWN)


if __name__=='__main__':
    unittest.main()
