"""Real FIFOs must fail promptly; run readers in killable child processes."""
import fcntl
import importlib.util
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/instances'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
P=load('fifo_instances','instances.py')
R=load('fifo_recovery','recovery.py')

class SpecialFileTests(unittest.TestCase):
    def bounded_reader(self,callback,lock):
        # Opening a FIFO without a writer used to block while holding the storage lock.
        context=multiprocessing.get_context('fork')
        receiver,sender=context.Pipe(duplex=False)
        def child():
            receiver.close()
            try:
                with lock.open('w') as stream:
                    fcntl.flock(stream,fcntl.LOCK_EX)
                    try:result=callback()
                    except P.PilotError as error:result=str(error)
                sender.send(result)
            finally:sender.close()
        process=context.Process(target=child);process.start();sender.close()
        try:
            self.assertTrue(receiver.poll(2),'reader blocked on a FIFO')
            result=receiver.recv();process.join(2)
            self.assertEqual(process.exitcode,0)
            with lock.open('w') as stream:
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            return result
        finally:
            if process.is_alive():process.terminate()
            process.join(2);receiver.close();process.close()

    def test_native_key_fifo_is_rejected_and_lock_released(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder);canvas=state/'.openhands'/'agent-canvas'
            canvas.mkdir(parents=True,mode=0o700);canvas.parent.chmod(0o700)
            os.mkfifo(canvas/'api-key.txt',0o600)
            tenant={'uid':os.getuid(),'gid':os.getgid()}
            with mock.patch.object(P,'paths',return_value=(state,state,state)):
                result=self.bounded_reader(lambda:P.key(tenant,'api-key.txt'),state/'lock')
            self.assertEqual(result,'unsafe_native_key_file')

    def test_marker_fifo_is_rejected_and_lock_released(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'marker';os.mkfifo(path,0o600)
            result=self.bounded_reader(lambda:R.marker_matches(path,{'uid':os.getuid(),'gid':os.getgid()},{'value':'synthetic'}),path.parent/'lock')
            self.assertIs(result,False)

    def test_manifest_fifo_is_rejected_and_lock_released(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'manifest';os.mkfifo(path,0o600)
            api=mock.Mock(PilotError=P.PilotError)
            result=self.bounded_reader(lambda:R.read_snapshot(api,{},path,'0'*64,owner=os.getuid()),path.parent/'lock')
            self.assertEqual(result,'unsafe_synthetic_manifest')

if __name__=='__main__':unittest.main()
