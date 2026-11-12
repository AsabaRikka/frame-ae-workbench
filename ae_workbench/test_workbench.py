import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class WorkbenchTests(unittest.TestCase):
    def test_output_comp_prefers_final_root_over_long_nested_comp(self):
        comps = [dict(name='合成 1', duration=600, uses=['Finish']), dict(name='Finish', duration=60, uses=[])]
        self.assertEqual(server.choose_output_comp(comps)['name'], 'Finish')

    def test_output_comp_preserves_legacy_main_name_without_graph(self):
        comps = [dict(name='小怪', duration=600), dict(name='总合成', duration=60)]
        self.assertEqual(server.choose_output_comp(comps)['name'], '总合成')

    def slots(self):
        return [dict(id=str(i), name=str(i), targets=[i], candidates=[dict(id=f'{i}-{j}', name=str(j), mapping={str(i):str(j)}) for j in range(n)]) for i,n in enumerate([5,5,2])]

    def test_fifty_combinations_are_unique(self):
        plans = server.build_plans(self.slots(), 50, 'repeatable')
        self.assertEqual(len({tuple(sorted(p['choices'].items())) for p in plans}), 50)

    def test_same_seed_repeats_choices(self):
        a = server.build_plans(self.slots(), 10, 'seed')
        b = server.build_plans(self.slots(), 10, 'seed')
        self.assertEqual([p['choices'] for p in a], [p['choices'] for p in b])

    def test_capacity_is_not_silently_padded(self):
        with self.assertRaisesRegex(ValueError, '50 种'):
            server.build_plans(self.slots(), 51, 'seed')

    def test_no_candidates_is_rejected(self):
        with self.assertRaises(ValueError):
            server.build_plans([], 1, 'seed')

    def test_overlapping_targets_are_rejected(self):
        fake = dict(scan=dict(items=[dict(id=1)]), assets=[])
        slots = [dict(id=str(i),name='test',targets=[1],candidates=[]) for i in range(2)]
        with patch.object(server, 'STATE', fake), self.assertRaisesRegex(ValueError, '两个替换位置'):
            server.validate_slots(slots)

    def test_incomplete_action_pack_is_rejected(self):
        fake = dict(scan=dict(items=[dict(id=1),dict(id=2)]), assets=[dict(id='a')])
        slots = [dict(name='enemy',targets=[1,2],candidates=[dict(mapping={'1':'a'})])]
        with patch.object(server, 'STATE', fake), self.assertRaisesRegex(ValueError, '每个目标'):
            server.validate_slots(slots)

    def test_duplicate_manual_plan_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'a.png'
            path.write_bytes(b'fixture')
            fake = dict(assets=[dict(id='a',path=str(path),sequence=False)], slots=[dict(id='s',candidates=[dict(id='c',mapping={'1':'a'})])])
            plan = dict(id='p',choices={'s':'c'})
            with patch.object(server,'STATE',fake), self.assertRaisesRegex(ValueError, '重复搭配'):
                server.dispatch('/api/save-plans',dict(plans=[plan,plan]))

    def test_missing_files_cannot_export(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'asset.png'
            path.write_bytes(b'fixture')
            fake = dict(scan=dict(items=[dict(id=1,name='a',missing=False),dict(id=2,name='missing',missing=True)],comps=[dict(name='comp')]),plans=[dict(id='p',name='test',choices={'s':'c'})],slots=[dict(id='s',name='slot',targets=[1],candidates=[dict(id='c',name='candidate',mapping={'1':'a'})])],assets=[dict(id='a',path=str(path),sequence=False)],comp='comp')
            with patch.object(server,'STATE',fake), self.assertRaisesRegex(ValueError,'暂不能导出完整视频'):
                server.dispatch('/api/export',dict(render=True))

    def test_project_only_generation_preserves_missing_warning(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'asset.png'
            path.write_bytes(b'fixture')
            fake = dict(project='test.aep',batches=[],scan=dict(items=[dict(id=1,name='a',missing=False),dict(id=2,name='missing',missing=True)],comps=[]),plans=[dict(id='p',name='test',choices={'s':'c'})],slots=[dict(id='s',name='slot',targets=[1],candidates=[dict(id='c',name='candidate',mapping={'1':'a'})])],assets=[dict(id='a',path=str(path),sequence=False)],comp='comp')
            with patch.object(server,'STATE',fake),patch.object(server,'BUSY',False),patch.object(server,'save'),patch.object(server.threading,'Thread'):
                result=server.dispatch('/api/export',dict(render=False))
                self.assertTrue(result['ok'])
                self.assertEqual(fake['batches'][0]['rows'][0]['missing'],['missing'])


if __name__ == '__main__':
    unittest.main()
