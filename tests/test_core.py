import copy
import json
import unittest
from pathlib import Path
import torch
from anima_character_sheet.catalog import DEFAULT, CONTRACT, ROOT, VIEWS
from anima_character_sheet.state import compact, parse_state, StateError, digest
from anima_character_sheet.compiler import compile_views, preview, view_seed
from anima_character_sheet.node import AnimaCharacterSheetDesigner as Designer
from anima_character_sheet.image_utils import tensor_rgb
from anima_character_sheet.tagger_node import AnimaImageTagger
from anima_character_sheet.assemble import AnimaCharacterSheetAssemble as Assemble

class Core(unittest.TestCase):
    def test_seed_vectors(self):
        for r in json.loads((ROOT/'contracts/seed_golden_vectors.json').read_text()):
            self.assertEqual(view_seed(r['base_seed'],r['view_id'],r['view_seed_offset']),r['seed'])

    def test_selection_independence(self):
        a=compile_views(DEFAULT)
        s=copy.deepcopy(DEFAULT);s['views']=VIEWS
        b={r['view_id']:r['seed'] for r in compile_views(s)}
        self.assertTrue(all(r['seed']==b[r['view_id']] for r in a))

    def test_presets(self):
        for views in CONTRACT['presets'].values():
            s=copy.deepcopy(DEFAULT);s['views']=views
            p=preview(compact(s))
            self.assertEqual(len(p['layout_plan']['panels']),len(views))
            self.assertLessEqual(p['width']*p['height'],2000000)

    def test_parts_scoped(self):
        s=copy.deepcopy(DEFAULT);s['views']=VIEWS;s['part_prompts']={'face':'FACE_MARK','other':'PERSON_MARK','upper_clothing':'COAT_MARK','back_clothing':'BACK_MARK','lower_body':'PANTS_MARK'}
        records={r['view_id']:r['positive'] for r in compile_views(s)}
        for v in ('clothing_front','clothing_back'):
            self.assertNotIn('FACE_MARK',records[v]);self.assertNotIn('PERSON_MARK',records[v]);self.assertIn('COAT_MARK',records[v]);self.assertIn('PANTS_MARK',records[v])
        self.assertNotIn('BACK_MARK',records['clothing_front']);self.assertIn('BACK_MARK',records['clothing_back'])
        self.assertNotIn('FACE_MARK',records['body_back'])

    def test_invalid_state(self):
        raw=compact(DEFAULT)
        for bad in [raw.replace('1120','1120.0'),raw.replace('1120','1.12e3'),raw.replace('1120','true'),raw.replace('"views":','"kind":"duplicate","views":'),raw.replace('anima_character_sheet','moss_image_character_sheet')]:
            with self.assertRaises(StateError):parse_state(bad)

    def test_unicode_and_limit(self):
        s=copy.deepcopy(DEFAULT);s['part_prompts']['face']='😀'*1000
        self.assertEqual(parse_state(compact(s))['part_prompts']['face'],s['part_prompts']['face'])
        s['part_prompts']['face']+='a'
        with self.assertRaises(StateError):parse_state(compact(s))

    def test_reference(self):
        image=torch.rand(1,24,32,3)
        self.assertEqual(tensor_rgb(image).shape,(24,32,3))
        with self.assertRaises(StateError):tensor_rgb(image,torch.ones(1,24,32))
        with self.assertRaises(StateError):tensor_rgb(image.repeat(2,1,1,1))
        with self.assertRaises(StateError):tensor_rgb(image,torch.zeros(1,12,16))
        alpha=torch.cat([image,torch.zeros(1,24,32,1)],-1)
        with self.assertRaises(StateError):tensor_rgb(alpha)

    def test_lazy_switch(self):
        d=AnimaImageTagger()
        self.assertEqual(d.check_lazy_status(use_image=False,manual_prompt=None,image=None),['manual_prompt'])
        self.assertEqual(d.check_lazy_status(use_image=True,manual_prompt=None,image=None),['image'])
        self.assertEqual(d.check_lazy_status(use_image=False,manual_prompt='A robot',image=None),[])
        with self.assertRaises(StateError):d.check_lazy_status(use_image=True)
        with self.assertRaises(StateError):d.check_lazy_status(use_image=False)

    def test_text_no_image(self):
        out=Designer().compile(compact(DEFAULT),use_image=False,prompt='An armored robot')
        self.assertEqual(len(out),6);self.assertEqual(len(out[0]),5)
        self.assertTrue(all('An armored robot' in p for p in out[0]))
        with self.assertRaises(StateError):Designer().compile(compact(DEFAULT),use_image=False,prompt=' ')

    def test_assembly_and_fail_closed(self):
        s=copy.deepcopy(DEFAULT);s['views']=['face_front','clothing_back']
        out=Designer().compile(compact(s),prompt='A robot in a coat')
        images=[torch.full((1,h,w,3),.2+.3*i) for i,(w,h) in enumerate(zip(out[1],out[2]))]
        sheet,info=Assemble().assemble(images,out[5],[out[4]])
        p=json.loads(out[4]);self.assertEqual(list(sheet.shape),[1,p['canvas'][1],p['canvas'][0],3])
        self.assertEqual(len(json.loads(info)['views']),2)
        with self.assertRaises(StateError):Assemble().assemble(images[:1],out[5],[out[4]])
        with self.assertRaises(StateError):Assemble().assemble(images,list(reversed(out[5])),[out[4]])
        with self.assertRaises(StateError):Assemble().assemble(images,out[5],[out[4],out[4]])
        p['canvas'][0]+=16
        with self.assertRaises(StateError):Assemble().assemble(images,out[5],[compact(p)])
        bad=images.copy();bad[0]=torch.zeros(1,16,16,3)
        with self.assertRaises(StateError):Assemble().assemble(bad,out[5],[out[4]])

    def test_editable_positive_and_external_negative(self):
        s=copy.deepcopy(DEFAULT);s['view_prompts']={'face_front':'own portrait,front,'}
        rows=compile_views(s, prompt='green eyes,short hair,')
        self.assertNotIn('masterpiece',rows[0]['positive'])
        self.assertIn('own portrait, front',rows[0]['positive'])
        self.assertNotIn('masterpiece',rows[0]['positive'])
        self.assertNotIn('negative', rows[0])
        self.assertFalse(rows[0]['positive'].endswith(','))
        self.assertNotRegex(rows[0]['positive'],r',(?=[^ ])')
        s['view_prompts']['face_front']=''
        self.assertNotIn('head and shoulders',compile_views(s)[0]['positive'])
        old=copy.deepcopy(DEFAULT);old['positive_common']='discarded';old.pop('view_prompts');old['negative_extra']='ignored'
        self.assertEqual(parse_state(compact(old)),DEFAULT)
        self.assertNotIn('negative',Designer.RETURN_NAMES)

    def test_footwear_auto_and_off(self):
        s=copy.deepcopy(DEFAULT);s['views']=['feet']
        self.assertIn('footwear only, no humans',compile_views(s)[0]['positive'])
        p=compile_views(s,prompt='1girl, red boots')[0]['positive']
        self.assertLess(p.index('red boots'),p.index('footwear only, no humans'))
        self.assertNotIn('soles',compile_views(s)[0]['positive'])
        s['appearance']['footwear_state']='unshod'
        self.assertIn('one pair of feet',compile_views(s)[0]['positive'])
        s['view_prompts']['feet']='custom boots'
        self.assertIn('custom boots',compile_views(s)[0]['positive'])

    def test_defaults_do_not_invent_hair_or_quality_tags(self):
        s=copy.deepcopy(DEFAULT);s['views']=['face_front','body_front'];s['subject_kind']='nonhuman'
        rows=compile_views(s,prompt='a smooth-headed creature')
        for row in rows:
            self.assertNotIn('hairstyle',row['positive'])
            self.assertNotIn('masterpiece',row['positive'])
            self.assertNotIn('score_7',row['positive'])

    def test_default_prompts_keep_normal_external_views(self):
        import re
        forbidden=re.compile(r'\b(?:anatom\w*|skelet\w*|skull|dissect\w*|cutaway|cross[- ]section|x[- ]ray|expos\w*|still life)\b',re.I)
        for group in ('views','view_definitions'):
            for definition in CONTRACT[group].values():
                self.assertIsNone(forbidden.search(definition['instruction']))
        s=copy.deepcopy(DEFAULT);s['views']=VIEWS
        for style in CONTRACT['styles']:
            s['style']=style
            for record in compile_views(s):
                self.assertIsNone(forbidden.search(record['positive']),record['view_id'])
        self.assertNotIn('gloves',CONTRACT['view_prompt_defaults']['hands'])
        self.assertEqual(CONTRACT['view_prompt_defaults']['clothing_front'],'The outfit is flat, front View of the outfit, no human, Remove the person')
        self.assertEqual(CONTRACT['view_prompt_defaults']['clothing_back'],'unworn clothes, The outfit is flat, (from behind:2), back of the outfit, no human, Remove the person')

    def test_source_scope_preserves_explicit_parts(self):
        s=copy.deepcopy(DEFAULT);s['views']=VIEWS;s['part_prompts']={'upper_clothing':'PURPLE_COAT'}
        records={x['view_id']:x['positive'] for x in compile_views(s,prompt='SOURCE_MARK')}
        for view in VIEWS:
            text=records[view];kind=CONTRACT['views'][view]['kind']
            if kind=='body':
                self.assertIn('Design description: SOURCE_MARK',text)
                self.assertNotIn('(SOURCE_MARK:0.5)',text)
            else:
                marker='(SOURCE_MARK:0.5)'
                self.assertLess(text.index(marker),text.index(CONTRACT['view_prompt_defaults'][view]))
        for view in ('clothing_front','clothing_back'):
            self.assertIn('PURPLE_COAT',records[view])
            self.assertNotIn('(PURPLE_COAT',records[view])

    def test_existing_render_format_and_square_manual_canvas(self):
        for views in (['feet'],VIEWS):
            for profile in CONTRACT['render_sizes']:
                s=copy.deepcopy(DEFAULT);s['views']=views;s['render_profile']=profile
                records={x['view_id']:x for x in compile_views(s)}
                self.assertEqual([records['feet']['width'],records['feet']['height']], [1152,896] if profile == 'standard' else [960,640])
                s['appearance']['footwear_state']='unshod'
                bare={x['view_id']:x for x in compile_views(s)}['feet']
                self.assertEqual([bare['width'],bare['height']],CONTRACT['render_sizes'][profile]['detail'])
        s=copy.deepcopy(DEFAULT);s['size'].update(mode='manual',manual_width=1024,manual_height=1024)
        self.assertEqual(preview(compact(s))['layout_plan']['canvas'],[1024,1024])

    def test_manual_thirteen(self):
        s=copy.deepcopy(DEFAULT);s['views']=VIEWS;s['size'].update(mode='manual',manual_width=512,manual_height=2048)
        p=preview(compact(s));self.assertEqual((p['width'],p['height']),(512,2048))
        self.assertEqual(len(p['view_prompts']),13)
        self.assertTrue(all('rect [' not in r['positive'] for r in p['view_prompts']))

if __name__=='__main__': unittest.main()
