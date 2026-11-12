import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import server
from catalog import inventory, validate_selection, descendants


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.scan = dict(items=[
            dict(id=1, name='untitled_843.png', sourceKind='file', uses=['子弹'], references=[dict(enabled=True)]),
            dict(id=2, name='Control', sourceKind='solid', uses=[], references=[]),
            dict(id=3, name='unused.png', sourceKind='file', uses=[], references=[]),
        ], comps=[
            dict(id=10, name='子弹', sourceKind='composition', uses=['Main'], references=[dict(enabled=True)], layers=[dict(sourceId=1)]),
            dict(id=11, name='Main', sourceKind='composition', uses=[], references=[], layers=[dict(sourceId=10)]),
        ], procedural=[dict(compId=11, compName='Main', layerIndex=2, layerName='分数', kind='text', text='100')])

    def test_unknown_names_and_unused_sources_are_not_hidden(self):
        entries = {e['id']: e for e in inventory(self.scan)}
        self.assertEqual(len(entries), 6)
        self.assertTrue(entries[1]['replaceable'])
        self.assertEqual(entries[1]['category'], '子弹')
        self.assertFalse(entries[3]['replaceable'])

    def test_nested_conflict_is_rejected(self):
        self.assertEqual(descendants(self.scan, 11), {1, 10})
        with self.assertRaisesRegex(ValueError, '不能同时'):
            validate_selection(self.scan, [1, 10])
        validate_selection(self.scan, [10])

    def test_roots_controls_and_generated_layers_not_direct_replacements(self):
        for item_id in [2, 11, 999]:
            with self.assertRaises(ValueError):
                validate_selection(self.scan, [item_id])
        self.assertFalse(inventory(self.scan)[-1]['replaceable'])

    def test_cycles_cannot_hang_discovery(self):
        self.scan['comps'][0]['layers'].append(dict(sourceId=11))
        self.assertEqual(descendants(self.scan, 10), {1, 11})

    def test_project_switch_restores_choices_without_changing_history(self):
        a = dict(project='A.aep', scan=self.scan, slots=[], plans=[], comp='Main',
                 catalogChoices={'1':dict(selected='A')}, simple=dict(folders={'enemy':'A folder'}), batches=[dict(id='existing')], assets=[])
        b = dict(project='B.aep', scan=self.scan, slots=[], plans=[], comp='Main',
                 catalogChoices={'1':dict(selected='B')}, simple=dict(folders={'enemy':'B folder'}))
        with tempfile.TemporaryDirectory() as temp, patch.object(server,'STATE',a), patch.object(server,'DATA',Path(temp)), patch.object(server,'save'), patch.object(server,'initialize_simple'):
            (Path(temp)/'projects').mkdir()
            server.write_json(Path(temp)/'projects'/(server.uid('b.aep')+'.json'),b)
            server.activate_project('B.aep')
            self.assertEqual(a['catalogChoices']['1']['selected'],'B')
            server.activate_project('A.aep')
            self.assertEqual(a['catalogChoices']['1']['selected'],'A')
            self.assertEqual(a['simple']['folders']['enemy'],'A folder')
            self.assertEqual(a['batches'],[dict(id='existing')])

    def test_stale_page_cannot_write_to_another_project(self):
        with patch.object(server,'STATE',dict(project='B.aep')), patch.object(server,'BUSY',False),patch.object(server,'SCANNING',False):
            with self.assertRaisesRegex(ValueError,'已切换'):
                server.dispatch('/api/catalog-select',dict(project='A.aep',target=1,clear=True))

    def test_group_export_snapshots_dimensions_and_does_not_change_manual_plans(self):
        with tempfile.TemporaryDirectory() as temp:
            media=Path(temp)/'replacement.png';media.write_bytes(b'fixture')
            scan=self.scan
            scan['comps'][0].update(width=100,height=80,path='',missing=False)
            scan['items']=[dict(e,missing=False)for e in scan['items']]
            state=dict(project='A.aep',scan=scan,assets=[dict(id='new',path=str(media),sequence=False,name='new')],
                       catalogChoices={'10':dict(assetIds=['new'],selected='new')},slots=[],plans=[dict(id='manual')],batches=[],comp='Main')
            with patch.object(server,'STATE',state),patch.object(server,'BUSY',False),patch.object(server,'SCANNING',False),patch.object(server,'save'),patch.object(server,'archive_project'),patch.object(server.threading,'Thread'):
                planned=server.dispatch('/api/catalog-plan',dict(project='A.aep',count=1))
                result=server.dispatch('/api/catalog-export',dict(project='A.aep',render=False,signature=planned['signature'],ids=[planned['plans'][0]['id']]))
                self.assertTrue(result['ok'])
                self.assertEqual(state['batches'][0]['sizeTargets']['10']['width'],100)
                self.assertEqual(state['batches'][0]['rows'][0]['replacements'][0]['itemId'],10)
                self.assertEqual(state['plans'],[dict(id='manual')])


if __name__ == '__main__':
    unittest.main()
