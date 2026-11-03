import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from anima_character_sheet.catalog import DEFAULT,ROOT,VIEWS
from anima_character_sheet.state import StateError,compact,digest
from anima_character_sheet.tagger_contracts import canonical,config,resource,profile,model_spec,hash_value,sha_text,load_json
from anima_character_sheet.tagger_node import AnimaImageTagger as Tagger,DEFAULT_CONFIG,effective_config
from anima_character_sheet.tagger_profile import filter_tags,build_profile,scoped_tags,literal
from anima_character_sheet.image_utils import preprocess,tensor_rgb,pixel_hash
from anima_character_sheet.node import AnimaCharacterSheetDesigner as Designer,generation_signature
from anima_character_sheet.compiler import compile_views
from anima_character_sheet.assemble import AnimaCharacterSheetAssemble as Assemble,validate_plan
from anima_character_sheet import tagger_backend as backend

class TaggerTests(unittest.TestCase):
    def test_output_contract_matches_native_socket_order_and_lists(self):
        outputs=resource('contracts/view_contract.v1.json')['outputs']
        self.assertEqual(tuple(x['name'] for x in outputs),Designer.RETURN_NAMES)
        self.assertEqual(tuple(x['type'] for x in outputs),Designer.RETURN_TYPES)
        self.assertEqual(tuple(x['is_list'] for x in outputs),Designer.OUTPUT_IS_LIST)

    def test_only_two_models_and_pixai_default(self):
        self.assertEqual(Tagger.INPUT_TYPES()['required']['model_id'][0],['pixai_v1_fp16','wd_eva02_large_v3'])
        self.assertEqual(resource('contracts/models.v1.json')['default_model'],'pixai_v1_fp16')
        with self.assertRaises(StateError):model_spec('pixai_v1_int8')

    def setUp(self):
        self.cfg=json.loads(DEFAULT_CONFIG);self.model=model_spec('pixai_v1_fp16')
        backend.clear_cache()

    def example(self):
        tags=[dict(name=n,category=0,score=.9) for n in ['1girl','blue_hair','green_eyes','coat','pants','boots','gloves','outdoors','sitting']]
        return build_profile(tags,self.cfg,self.model,'a'*64)

    def test_native_flags_preserve_old_api_and_override_false(self):
        cfg=dict(self.cfg,include_character=True,include_copyright=True,multi_subject_policy='allow_with_warning')
        self.assertEqual(effective_config(canonical(cfg)),cfg)
        actual=effective_config(canonical(cfg),False,False,False)
        self.assertFalse(actual['include_character']);self.assertFalse(actual['include_copyright']);self.assertEqual(actual['multi_subject_policy'],'block')
        with self.assertRaises(StateError):effective_config(DEFAULT_CONFIG,1)
        # Backend flags are actual optional inputs and survive linked-widget promotion.
        options=Tagger.INPUT_TYPES()['optional']
        for key in ('include_character','include_copyright','allow_multiple_subjects'):self.assertEqual(options[key][0],'BOOLEAN')

    def test_fp16_preprocessing_and_profile_can_reach_designer(self):
        model=model_spec('pixai_v1_fp16');rgb=np.zeros((7,4,3),np.uint8)
        text,p,_=build_profile([dict(name='brown_hair',category=0,score=.9)],self.cfg,model,'a'*64)
        self.assertEqual(profile(canonical(p),text),p)
        result=Designer().compile(compact(DEFAULT),prompt=text,profile_json=canonical(p))
        self.assertEqual(len(result),6)
        validate_plan(json.loads(result[4]))

    def test_cuda_allows_cpu_auxiliary_operators_but_rejects_cpu_replacement(self):
        from types import SimpleNamespace
        providers=[]
        class Session:
            def __init__(self,path,sess_options,providers): self.providers=providers
            def disable_fallback(self):pass
            def get_providers(self):return providers
            def get_inputs(self):return [SimpleNamespace(name='input',type='tensor(float)',shape=[1,3,1008,1008])]
            def get_outputs(self):return [SimpleNamespace(name='prediction',type='tensor(float)',shape=[1,30877])]
            def run(self,*args):return [np.zeros((1,30877),np.float32)]
        ort=SimpleNamespace(SessionOptions=SimpleNamespace,InferenceSession=Session,get_available_providers=lambda:['CUDAExecutionProvider','CPUExecutionProvider'])
        providers[:]=['CUDAExecutionProvider','CPUExecutionProvider']
        _,d=backend.run_session(ort,Path('test.onnx'),self.model,None,'cuda',0)
        self.assertEqual(d['actual_device'],'cuda');self.assertEqual(d['providers'],providers)
        providers[:]=['CPUExecutionProvider']
        with self.assertRaises(backend.ProviderUnavailable):backend.run_session(ort,Path('test.onnx'),self.model,None,'cuda',0)

    def test_manual_exact_and_bypasses_all_model_image_work(self):
        value='  日本語, user (weights:1.2)\n background, score_7  '
        with patch('anima_character_sheet.tagger_models.model_files',side_effect=AssertionError),patch('anima_character_sheet.image_utils.tensor_rgb',side_effect=AssertionError),patch.object(backend,'infer',side_effect=AssertionError):
            out=Tagger().tag(manual_prompt=value,image=object(),config_json='invalid',model_id='absent')['result']
            self.assertEqual(out[0],value);self.assertEqual(out[1:3],('',''))
            self.assertTrue(Tagger.VALIDATE_INPUTS(False,value,'invalid','absent'))
            self.assertEqual(Tagger.IS_CHANGED(False,value),('manual',value))
            self.assertTrue(Tagger.VALIDATE_INPUTS(None,None,'invalid','absent'))
            first=Tagger.IS_CHANGED(None,config_json='invalid'); second=Tagger.IS_CHANGED(None,config_json='invalid')
            self.assertNotEqual(first,second);json.dumps({'is_changed':[first]},allow_nan=False)
        for invalid in ('',' ','x'*4001,'\ud800'):
            with self.assertRaises(StateError):Tagger().tag(manual_prompt=invalid)

    def test_manual_sixteen_baselines_unchanged(self):
        data=json.loads((ROOT/'tests/tagger-manual-baseline.json').read_text('utf-8'))
        self.assertEqual(len(data['cases']),16)
        for case in data['cases']:
            with self.subTest(case=case['id']):self.assertEqual(compile_views(case['state'],case['base_seed'],case['prompt']),case['records'])

    def test_filter_vectors(self):
        for case in resource('tests/tagger_spec/fixtures/filter_vectors.json')['cases']:
            with self.subTest(case=case['id']):
                if 'error' in case['expected']:
                    with self.assertRaisesRegex(StateError,case['expected']['error']):filter_tags(case['tags'],self.cfg,self.model)
                else:
                    actual=filter_tags(case['tags'],self.cfg,self.model)
                    self.assertEqual(actual['groups'],case['expected']['groups'])
                    for key in ('excluded','review'):
                        self.assertEqual([{k:t[k] for k in ('name','reason')} for t in actual[key]],case['expected'][key])

    def test_json_boundary(self):
        for value in ('{"a":1,"a":2}','{"a":NaN}','{"a":1e999}','"\\ud800"'):
            with self.assertRaises(StateError):load_json(value)
        for key,value in [('max_tags',2.0),('max_tags',True),('device_id',-1),('include_character',1)]:
            cfg=copy.deepcopy(self.cfg);cfg[key]=value
            with self.assertRaises(StateError):config(canonical(cfg))
        cfg=copy.deepcopy(self.cfg);cfg['thresholds']['general']=True
        with self.assertRaises(StateError):config(canonical(cfg))
        cfg['thresholds']['general']=.25;self.assertEqual(config(canonical(cfg)),cfg)

    def test_profile_hash_prompt_and_scope(self):
        text,p,_=self.example();self.assertEqual(profile(canonical(p),text),p)
        with self.assertRaisesRegex(StateError,'E_PROFILE_PROMPT_MISMATCH'):profile(canonical(p),text+' extra')
        p['groups']['feet'].append('blue_hair');p['profile_hash']=hash_value({k:v for k,v in p.items() if k!='profile_hash'})
        with self.assertRaisesRegex(StateError,'E_PROFILE_GROUP'):profile(canonical(p),text)
        text,p,_=self.example();state=copy.deepcopy(DEFAULT);state['views']=VIEWS
        rows={r['view_id']:r['positive'] for r in compile_views(state,42,text,p)}
        for view in ('clothing_front','clothing_back','hands','feet'):
            self.assertNotIn('blue hair',rows[view]);self.assertNotIn('green eyes',rows[view]);self.assertNotIn('1girl',rows[view])
        self.assertNotIn('outdoors',str(rows));self.assertNotIn('sitting',str(rows))
        self.assertIn('boots',rows['feet']);self.assertNotIn('coat',rows['feet'])
        state['appearance']['hand_state']='bare';state['appearance']['footwear_state']='unshod'
        self.assertNotIn('boots',scoped_tags(p,'feet',state));self.assertNotIn('gloves',scoped_tags(p,'hands',state))

    def test_explicit_parts_survive_empty_clothing(self):
        self.cfg['scope_additions']={'feet':['my_boots']}
        text,p,_=build_profile([dict(name='blue_hair',category=0,score=.9)],self.cfg,self.model,'a'*64)
        state=copy.deepcopy(DEFAULT);state['views']=['clothing_back'];state['part_prompts']['back_clothing']='gold trim'
        state['appearance']['clothing_type']='pants'
        row=compile_views(state,42,text,p)[0]['positive']
        self.assertIn('gold trim',row);self.assertIn('trousers',row);self.assertNotIn('Blank',row)

    def test_explicit_choices_filter_only_opposing_automatic_tags(self):
        tags=['1girl','blue_coat','skirt','black_skirt','pants','red_pants','shorts','belt','mittens','gloves','bare_hands','nail_polish','barefoot','boots','socks']
        text,p,review=build_profile([dict(name=t,category=0,score=.9) for t in tags],self.cfg,self.model,'a'*64)
        before=canonical(p);before_review=canonical(review)
        for field,value,removed,retained in [
            ('clothing_type','pants',['skirt','black skirt'],['blue coat','pants','belt']),
            ('clothing_type','skirt_robe',['pants','red pants','shorts'],['blue coat','skirt','belt']),
            ('hand_state','bare',['mittens','gloves'],['nail polish','blue coat']),
            ('hand_state','gloved',['bare hands'],['mittens','nail polish']),
            ('footwear_state','shod',['barefoot'],['boots','socks']),
            ('footwear_state','unshod',['boots'],['socks','blue coat']),
        ]:
            with self.subTest(field=field,value=value):
                state=copy.deepcopy(DEFAULT);state['appearance'][field]=value
                actual=scoped_tags(p,'body_front',state).split(', ')
                for tag in removed:self.assertNotIn(tag,actual)
                for tag in retained:self.assertIn(tag,actual)
        self.assertEqual(canonical(p),before);self.assertEqual(canonical(review),before_review)
        self.assertIn('black skirt',scoped_tags(p,'body_front',DEFAULT))
        self.cfg['scope_additions']={'hands':['mittens'],'lower_outfit':['skirt']}
        t2,p2,_=build_profile([dict(name='blue_coat',category=0,score=.9)],self.cfg,self.model,'a'*64)
        state=copy.deepcopy(DEFAULT);state['appearance'].update(clothing_type='pants',hand_state='bare')
        self.assertIn('mittens',scoped_tags(p2,'hands',state));self.assertIn('skirt',scoped_tags(p2,'clothing_front',state))
        state['views']=['body_front'];state['part_prompts']['lower_body']='skirt over trousers'
        self.assertIn('skirt over trousers',compile_views(state,42,t2,p2)[0]['positive'])

    def test_multiple_checked_before_user_exclusions(self):
        self.cfg['exclude_tags']=['2girls']
        with self.assertRaisesRegex(StateError,'E_MULTIPLE_SUBJECTS'):build_profile([dict(name='2girls',category=0,score=.9)],self.cfg,self.model,'a'*64)
        with self.assertRaisesRegex(StateError,'E_APPEARANCE_EMPTY'):build_profile([dict(name='outdoors',category=0,score=.9)],self.cfg,self.model,'a'*64)

    def test_literal_not_emphasis(self):
        self.assertEqual(literal('score_7'),'score_7')
        self.assertEqual(literal('NAME_(test):[x]'),r'name \(test\)\:\[x\]')

    def test_preprocess_colors_padding_and_masks(self):
        red=np.full((20,10,3),[255,0,0],np.uint8)
        pix=preprocess(red,'pixai_v1_fp16');wd=preprocess(red,'wd_eva02_large_v3')
        self.assertEqual(pix.shape,(1,3,1008,1008));self.assertEqual(wd.shape,(1,448,448,3))
        np.testing.assert_array_equal(pix[0,:,504,504],[1,-1,-1]);np.testing.assert_array_equal(pix[0,:,0,0],[-1,-1,-1])
        np.testing.assert_array_equal(wd[0,224,224],[0,0,255]);np.testing.assert_array_equal(wd[0,0,0],[255,255,255])
        x=torch.zeros(1,20,10,3);np.testing.assert_array_equal(tensor_rgb(x,torch.zeros(1,64,64)),0)
        rgba=torch.cat([x,torch.full((1,20,10,1),.5)],-1);np.testing.assert_array_equal(tensor_rgb(rgba),128)
        with self.assertRaises(StateError):tensor_rgb(rgba,torch.zeros(1,20,10))
        self.assertNotEqual(pixel_hash(red),pixel_hash(red.transpose(1,0,2).copy()))

    def test_probabilities_not_double_sigmoid(self):
        a=np.array([[0,.2,1]],dtype=np.float32);np.testing.assert_array_equal(backend.validate_scores(a,3),a[0])
        for bad in (np.array([[np.nan]]),np.array([[1.01]]),np.zeros((2,1)),np.zeros((1,1),np.int64)):
            with self.assertRaises(StateError):backend.validate_scores(bad,1)

    def test_provider_fallback_and_cache(self):
        rgb=np.zeros((4,4,3),np.uint8);calls=[]
        def run(ort,path,model,tensor,device,device_id):
            calls.append((str(path),device))
            if device=='cuda':raise backend.ProviderUnavailable('missing')
            return np.zeros(3,np.float32),dict(actual_device=device)
        with patch.object(backend,'fingerprint',return_value='test'),patch.object(backend,'run_session',side_effect=run):
            a,d=backend.infer(Path('.'),self.model,rgb,'hash','auto');self.assertEqual([d for _,d in calls],['cuda','cpu'])
            self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(d['fallback_reason'],'cuda_provider_unavailable')
            _,d=backend.infer(Path('.'),self.model,rgb,'hash','auto');self.assertTrue(d['cache_hit']);self.assertEqual(len(calls),2)
            backend.infer(Path('.'),self.model,rgb,'newimage','auto');self.assertEqual(calls[-1][1],'cpu');self.assertEqual(len(calls),3)
            with self.assertRaisesRegex(StateError,'E_GPU_UNAVAILABLE'):backend.infer(Path('.'),self.model,rgb,'forced','cuda')
            backend.infer(Path('.'),self.model,rgb,'hash','auto',refresh_nonce=1);self.assertEqual([d for _,d in calls[-2:]],['cuda','cpu'])

    def test_fatal_gpu_or_cancel_never_retry_cpu(self):
        for error in (RuntimeError('CUDA illegal memory access'),RuntimeError('cancelled'),RuntimeError('invalid input shape')):
            backend.clear_cache()
            with patch.object(backend,'fingerprint',return_value='test'),patch.object(backend,'run_session',side_effect=error) as run:
                with self.assertRaises(RuntimeError):backend.infer(Path('.'),self.model,np.zeros((4,4,3),np.uint8),'hash','auto')
                self.assertEqual(run.call_count,1)

    def test_plan_hash_and_generation_binding(self):
        text,p,_=self.example();state=copy.deepcopy(DEFAULT);state['views']=['feet']
        out=Designer().compile(compact(state),prompt=text,profile_json=canonical(p))
        plan=json.loads(out[4]);validate_plan(plan)
        self.assertEqual(plan['input_source']['mode'],'image_tags');self.assertEqual(len(out),6)
        image=torch.zeros(1,out[2][0],out[1][0],3)
        Assemble().assemble([image],out[5],[out[4]])
        r=json.loads(out[5][0]);r['positive']+=' tampered'
        with self.assertRaisesRegex(StateError,'E_GENERATION_SIGNATURE'):Assemble().assemble([image],[compact(r)],[out[4]])
        r['schema_version']=1
        with self.assertRaises(StateError):Assemble().assemble([image],[compact(r)],[out[4]])

    def test_legacy_plan_accepted_but_direct_adapter_rejected(self):
        state=copy.deepcopy(DEFAULT);state['views']=['feet'];out=Designer().compile(compact(state),prompt='black boots')
        plan=json.loads(out[4]);plan.pop('input_source');plan.pop('generation_signature');plan.update(schema_version=1,compiler_revision='anima-sheet-1.0.3',reference_hash='a'*64)
        plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'})
        r=json.loads(out[5][0]);r.update(schema_version=1,sheet_plan_hash=plan['plan_hash'])
        Assemble().assemble([torch.zeros(1,out[2][0],out[1][0],3)],[compact(r)],[compact(plan)])
        with self.assertRaisesRegex(StateError,'E_LEGACY_REFERENCE_REMOVED'):Designer().compile(compact(state),prompt='boots',use_image=True)

if __name__=='__main__':unittest.main()
