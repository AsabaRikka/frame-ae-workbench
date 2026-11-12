import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server
from folder_browser import browse_files


class CatalogPlanTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        for name in ['a.png','b.png','seq/walk_00.png','seq/walk_01.png','other/c.png']:
            path=self.root/name;path.parent.mkdir(exist_ok=True);Image.new('RGBA',(16,16),(255,0,0,255)).save(path)
        items=[dict(id=i,name=f'target{i}',path=str(self.root/'a.png'),sourceKind='file',uses=['Main'],references=[dict(enabled=True)],missing=False,still=i!=2,width=16,height=16) for i in [1,2,3]]
        self.state=dict(project='A.aep',scan=dict(items=items,comps=[dict(id=10,name='Main',sourceKind='composition',uses=[],layers=[])],scannedAt='test'),assets=[],catalogChoices={},batches=[],comp='Main')
        for name,value in [('STATE',self.state),('BUSY',False),('SCANNING',False)]:self.stack.enter_context(patch.object(server,name,value))
        self.stack.enter_context(patch.object(server,'save'));self.stack.enter_context(patch.object(server,'archive_project'))
    def call(self,action,**kwargs):return server.dispatch('/api/'+action,dict(project='A.aep',**kwargs))
    def add(self,target,name):return self.call('catalog-select',target=target,file=str(self.root/name))

    def test_single_numbered_frame_stays_single_and_does_not_merge_sequence(self):
        single=server.collect_assets(self.root/'seq/walk_00.png',allow_file=True)[0]
        sequence=server.collect_assets(self.root/'seq')[0]
        self.assertFalse(single['sequence']);self.assertTrue(sequence['sequence'])
        self.assertNotEqual(single['id'],sequence['id'])
        self.assertEqual(len(browse_files(str(self.root/'seq'),server.EXTENSIONS)['files']),2)

    def test_append_from_multiple_places_deduplicates_and_preserves_other_targets(self):
        self.add(1,'a.png');self.add(1,'other/c.png');self.add(3,'b.png');self.add(1,'a.png')
        self.assertEqual(len(self.state['catalogChoices']['1']['selectedIds']),2)
        self.assertEqual(len(self.state['catalogChoices']['3']['selectedIds']),1)
        self.assertEqual(len(self.state['assets']),3)

    def test_sequence_target_requires_folder_and_keeps_sequence_grouping(self):
        with self.assertRaisesRegex(ValueError,'序列帧'):self.add(2,'a.png')
        self.call('catalog-select',target=2,folder=str(self.root/'seq'))
        self.assertTrue(self.state['assets'][0]['sequence'])
        self.call('catalog-select',target=2,folder=str(self.root/'other'))
        self.assertEqual(len(self.state['catalogChoices']['2']['assetIds']),2)

    def test_preview_and_export_use_identical_selected_plans(self):
        for target in [1,3]:
            for name in ['a.png','b.png']:self.add(target,name)
        planned=self.call('catalog-plan',count=4)
        self.assertEqual(len({tuple(p['choices'].values()) for p in planned['plans']}),4)
        chosen=planned['plans'][2]
        with patch.object(server,'enqueue_export',return_value={'ok':True}) as enqueue:
            self.call('catalog-export',signature=planned['signature'],ids=[chosen['id']],render=False)
            self.assertEqual(enqueue.call_args.kwargs['selected'],[chosen['id']])
            self.assertEqual(enqueue.call_args.args[0][2]['choices'],chosen['choices'])
        with self.assertRaises(ValueError):self.call('catalog-plan',count=5)
        with self.assertRaises(ValueError):self.call('catalog-export',signature=planned['signature'],ids=['unknown'])

    def test_selected_plan_count_and_replacements_become_exact_batch_rows(self):
        self.add(1,'a.png');self.add(1,'b.png');self.add(3,'a.png');self.add(3,'b.png')
        planned=self.call('catalog-plan',count=4);selected=planned['plans'][1:3]
        expected=[server.resolve_plan(p,server.catalog_slots(),{a['id']:a for a in self.state['assets']}) for p in selected]
        with patch.object(server.threading,'Thread'):
            self.call('catalog-export',signature=planned['signature'],ids=[p['id'] for p in selected],render=False)
        rows=self.state['batches'][0]['rows'];self.assertEqual(len(rows),2)
        self.assertEqual([r['id'] for r in rows],[p['id'] for p in selected])
        self.assertEqual([[r['path'] for r in row['replacements']] for row in rows],[[r['path'] for r in result] for result in expected])

    def test_duplicate_edits_rejected_without_overwriting_saved_plans(self):
        self.add(1,'a.png');self.add(1,'b.png');planned=self.call('catalog-plan',count=2)
        edited=copy.deepcopy(planned['plans']);edited[1]['choices']=dict(edited[0]['choices'])
        with self.assertRaisesRegex(ValueError,'重复'):self.call('catalog-plan-save',signature=planned['signature'],plans=edited)
        self.assertNotEqual(self.state['catalogPlans'][0]['choices'],self.state['catalogPlans'][1]['choices'])

    def test_candidate_change_invalidates_plans_and_stale_export(self):
        self.add(1,'a.png');planned=self.call('catalog-plan',count=1);self.add(1,'b.png')
        self.assertEqual(self.state['catalogPlans'],[])
        with self.assertRaises(ValueError):self.call('catalog-export',signature=planned['signature'],ids=[planned['plans'][0]['id']])

    def test_uncheck_and_remove_do_not_delete_media(self):
        self.add(1,'a.png');self.add(1,'b.png');ids=self.state['catalogChoices']['1']['assetIds']
        self.call('catalog-select',target=1,selectedIds=[ids[1]])
        self.assertEqual(len(server.catalog_slots()[0]['candidates']),1)
        self.call('catalog-select',target=1,removeId=ids[0])
        self.assertTrue((self.root/'a.png').exists())
        self.assertEqual(self.state['catalogChoices']['1']['assetIds'],[ids[1]])

    def test_large_combination_space_does_not_overflow(self):
        slots=[dict(id=str(i),candidates=[dict(id=str(j)) for j in range(10)]) for i in range(30)]
        plans=server.build_plans(slots,50,'seed')
        self.assertEqual(len({tuple(p['choices'].values()) for p in plans}),50)


if __name__=='__main__':unittest.main()
