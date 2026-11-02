import hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from anima_character_sheet import tagger_models as models
from anima_character_sheet import tagger_download as service
from anima_character_sheet.state import StateError

class DownloadTests(unittest.TestCase):
    def test_verified_download_progress_reuse_and_mismatch_protection(self):
        data=b'test weights';meta=b'name,category\ncoat,0\n'
        def entry(name,content):return dict(filename=name,size=len(content),sha256=hashlib.sha256(content).hexdigest())
        model=dict(id='fixture',repo_id='owner/repo',revision='pinned',**entry('model.onnx',data),metadata=entry('tags.csv',meta))
        with tempfile.TemporaryDirectory() as tmp,patch.object(models,'roots',return_value=(Path(tmp),[Path(tmp)])),patch.object(models,'interrupt'):
            events=[]
            with patch('urllib.request.urlopen',side_effect=[io.BytesIO(data),io.BytesIO(meta)]) as request:
                path=models.download_model(model,lambda *args:events.append(args))
                self.assertEqual(request.call_count,2)
            self.assertEqual((path/'model.onnx').read_bytes(),data)
            receipt=models.download_info(path,model)
            self.assertIsNotNone(receipt['downloaded_at'])
            self.assertEqual(events[-1][:3],('ready',len(data)+len(meta),len(data)+len(meta)))
            self.assertEqual(list(path.glob('*.part')),[])
            with patch('urllib.request.urlopen',side_effect=AssertionError('existing weights redownloaded')):
                self.assertEqual(models.download_model(model),path)
                self.assertEqual(models.download_info(path,model)['downloaded_at'],receipt['downloaded_at'])
                (path/'model.onnx').write_bytes(b'protected custom weights')
                with self.assertRaisesRegex(StateError,'E_MODEL_HASH'):models.download_model(model)
            self.assertEqual((path/'model.onnx').read_bytes(),b'protected custom weights')

    def test_bad_download_removes_partial_but_not_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(models,'roots',return_value=(Path(tmp),[Path(tmp)])),patch.object(models,'interrupt'):
            model=dict(id='fixture',repo_id='owner/repo',revision='pinned',filename='model.onnx',size=4,sha256='0'*64,metadata=dict(filename='tags.csv',size=1,sha256='0'*64))
            directory=Path(tmp)/'fixture';directory.mkdir();(directory/'unrelated.txt').write_text('keep')
            with patch('urllib.request.urlopen',return_value=io.BytesIO(b'bad!')):
                with self.assertRaisesRegex(StateError,'E_MODEL_HASH'):models.download_model(model)
            self.assertEqual([p.name for p in directory.iterdir()],['unrelated.txt'])

    def test_status_never_downloads_and_explicit_request_can_retry(self):
        service._jobs.clear()

        class ImmediateThread:
            def __init__(self,target,args,**kwargs):self.target=target;self.args=args
            def start(self):self.target(*self.args)
        with tempfile.TemporaryDirectory() as tmp,patch.object(service,'roots',return_value=(Path(tmp),[])),patch.object(service,'Thread',ImmediateThread),patch.object(service,'model_files',side_effect=StateError('E_MODEL_MISSING','model','missing')),patch.object(service,'download_model',return_value=Path(tmp)) as download:
            result=service.status('pixai_v1_fp16');self.assertEqual(result['state'],'missing');download.assert_not_called()
            result=service.status('pixai_v1_fp16',True);self.assertEqual(result['state'],'ready');download.assert_called_once()
            self.assertEqual(result['completed'],result['total'])
            with self.assertRaises(StateError):service.status('../../unknown',True)
        service._jobs.clear()

    def test_existing_files_do_not_invent_download_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'model.onnx').write_bytes(b'existing')
            model=dict(filename='model.onnx',sha256='locked',revision='pinned')
            info=models.download_info(p,model)
            self.assertIsNone(info['downloaded_at']);self.assertIsNotNone(info['file_modified_at'])
            (p/'.anima-download.json').write_text('{broken')
            self.assertIsNone(models.download_info(p,model)['downloaded_at'])

if __name__=='__main__':unittest.main()
