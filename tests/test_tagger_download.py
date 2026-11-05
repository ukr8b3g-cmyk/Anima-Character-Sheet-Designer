import hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from anima_character_sheet import tagger_models as models
from anima_character_sheet import tagger_download as service
from anima_character_sheet.state import StateError

class DownloadTests(unittest.TestCase):
    def test_concurrent_acquisition_reuses_completed_files(self):
        from concurrent.futures import ThreadPoolExecutor
        data=b'weights';meta=b'name,category\ncoat,0\n'
        def entry(name,content):return dict(filename=name,size=len(content),sha256=hashlib.sha256(content).hexdigest())
        model=dict(id='fixture',repo_id='owner/repo',revision='pinned',**entry('model.onnx',data),metadata=entry('tags.csv',meta))
        with tempfile.TemporaryDirectory() as tmp,patch.object(models,'roots',return_value=(Path(tmp),[Path(tmp)])),patch.object(models,'interrupt'),patch('urllib.request.urlopen',side_effect=[io.BytesIO(data),io.BytesIO(meta)]) as request:
            with ThreadPoolExecutor(max_workers=2) as pool:
                paths=list(pool.map(lambda _:models.model_files(model,True),range(2)))
            self.assertEqual(paths[0],paths[1]);self.assertEqual(request.call_count,2)
            self.assertEqual(list(paths[0].glob('*.part')),[])

    def test_image_execution_acquires_selected_model_but_manual_never_does(self):
        from anima_character_sheet.tagger_node import AnimaImageTagger
        with patch.object(models,'model_files',side_effect=RuntimeError('download boundary')) as acquire,patch.object(models,'interrupt'),patch.object(models,'refresh_model'),patch('anima_character_sheet.image_utils.tensor_rgb',return_value=object()),patch('anima_character_sheet.image_utils.pixel_hash',return_value='fixture'):
            node=AnimaImageTagger()
            node.tag(use_image=False,manual_prompt='manual prompt');acquire.assert_not_called()
            for model in ('pixai_v1_fp16','wd_eva02_large_v3'):
                with self.assertRaisesRegex(RuntimeError,'download boundary'):node.tag(use_image=True,model_id=model,image=object(),allow_download=False)
                self.assertEqual(acquire.call_args.args[0]['id'],model)
                self.assertIs(acquire.call_args.args[1],True)

    def test_recheck_and_expiry_follow_real_file_install_remove_and_repair(self):
        class ImmediateThread:
            def __init__(self,target,args,**kwargs): self.target=target;self.args=args
            def start(self): self.target(*self.args)
        weights=b'fixture';meta=b'name,category\nboots,0\n'
        def entry(name,data):return dict(filename=name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        model=dict(id='fixture',repo_id='audit/fixture',revision='fixed',**entry('model.onnx',weights),metadata=entry('tags.csv',meta))
        previous_jobs=dict(service._jobs);previous_times=dict(service._checked_at)
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.object(service,'model_spec',return_value=model),patch.object(service,'roots',return_value=(Path(tmp),[Path(tmp)])),patch.object(models,'roots',return_value=(Path(tmp),[Path(tmp)])),patch.object(service,'Thread',ImmediateThread),patch.object(service,'download_model',side_effect=AssertionError('Recheck downloaded files')),patch.object(models,'interrupt'),patch.object(service,'monotonic',return_value=100) as clock:
                service._jobs.clear();service._checked_at.clear()
                self.assertEqual(service.status('fixture')['state'],'missing')
                directory=Path(tmp)/'fixture';directory.mkdir()
                (directory/'model.onnx').write_bytes(weights);(directory/'tags.csv').write_bytes(meta)
                self.assertEqual(service.status('fixture',refresh=True)['state'],'ready')
                (directory/'model.onnx').unlink();clock.return_value+=service.STATUS_TTL+1
                self.assertEqual(service.status('fixture')['state'],'missing')
                (directory/'model.onnx').write_bytes(b'wrong!!')
                self.assertEqual(service.status('fixture',refresh=True)['state'],'error')
                (directory/'model.onnx').write_bytes(weights)
                self.assertEqual(service.status('fixture',refresh=True)['state'],'ready')
        finally:
            service._jobs.clear();service._jobs.update(previous_jobs)
            service._checked_at.clear();service._checked_at.update(previous_times)

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


class ModelStatusRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_refresh_rechecks_without_a_download(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        class ImmediateThread:
            def __init__(self,target,args,**kwargs):self.target=target;self.args=args
            def start(self):self.target(*self.args)
        present=[False]
        def model_files(*args,**kwargs):
            if not present[0]:raise StateError('E_MODEL_MISSING','fixture','missing')
            return Path('fixture')
        old_jobs=dict(service._jobs);old_times=dict(service._checked_at)
        try:
            service._jobs.clear();service._checked_at.clear()
            routes=web.RouteTableDef();service.register_routes(routes);app=web.Application();app.add_routes(routes)
            with patch.object(service,'Thread',ImmediateThread),patch.object(service,'roots',return_value=(Path('fixture'),[])),patch.object(service,'model_files',side_effect=model_files),patch.object(service,'download_info',return_value={}),patch.object(service,'download_model',side_effect=AssertionError('GET downloaded files')):
                async with TestClient(TestServer(app)) as client:
                    endpoint='/anima_character_sheet_designer/v1/models/pixai_v1_fp16'
                    self.assertEqual((await (await client.get(endpoint)).json())['state'],'missing')
                    present[0]=True
                    self.assertEqual((await (await client.get(endpoint+'?refresh=1')).json())['state'],'ready')
                    present[0]=False
                    self.assertEqual((await (await client.get(endpoint+'?refresh=1')).json())['state'],'missing')
        finally:
            service._jobs.clear();service._jobs.update(old_jobs)
            service._checked_at.clear();service._checked_at.update(old_times)

if __name__=='__main__':unittest.main()
