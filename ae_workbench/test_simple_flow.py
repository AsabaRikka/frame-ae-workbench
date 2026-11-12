import tempfile
import unittest
from pathlib import Path
from simple_flow import analyze_folders
import server


def target(id, name, uses, still=False):
    return dict(id=id,name=name,uses=uses,still=still,path=name,missing=True)


class SimpleFlowTests(unittest.TestCase):
    def setUp(self):
        self.scan=dict(items=[target(1,'背景.png',['背景'],True),target(2,'tianbing-move_[00-11].png',['小怪']),target(3,'xiaoguai-move_[00-31].png',[]),target(4,'screenshot.png',['第一组小怪'],True),target(5,'juese-die_[00-24].png',['小怪死亡']),target(6,'boss-move_[00-39].png',['boss_move']),target(7,'boss-attack_[00-29].png',['boss_gongji']),target(8,'zz_jyg-move.png',['黄金宝箱 合成 12'])])

    def analyze(self, role, names):
        with tempfile.TemporaryDirectory() as temp:
            assets=[]
            for index,name in enumerate(names):
                path=Path(temp)/name
                assets.append(dict(id=str(index),name=path.stem,path=str(path),extension='.png',frames=32,sequence=True))
            return analyze_folders(self.scan,{role:temp},lambda _:assets)

    def test_move_only_does_not_replace_screenshot_death_unused_or_background(self):
        report=self.analyze('enemy',['xiaoguai-move.png'])
        self.assertTrue(report['canGenerate'])
        self.assertEqual(report['slots'][0]['targets'],[2])
        self.assertEqual(report['roles'][1]['retained'][0]['action'],'死亡')
        self.assertFalse(report['canRender'])

    def test_background_rejects_accidental_character_folder(self):
        report=self.analyze('background',['xiaoguai-move.png'])
        self.assertFalse(report['canGenerate'])
        self.assertIn('角色动作',report['issues'][0])

    def test_background_folder_supports_multiple_candidates(self):
        report=self.analyze('background',['forest.png','desert.png'])
        self.assertEqual(report['total'],2)
        self.assertEqual(report['slots'][0]['targets'],[1])

    def test_bg_filename_is_background_in_new_project(self):
        self.scan['items'][0]['name'] = 'bg.png'
        report=self.analyze('background',['forest.png'])
        self.assertTrue(report['canGenerate'])
        self.assertEqual(report['slots'][0]['targets'],[1])

    def test_boss_actions_group_together_and_exclude_chest_sprite(self):
        report=self.analyze('boss',['robot-move.png','robot-attack.png'])
        self.assertEqual(report['total'],1)
        self.assertEqual(set(report['slots'][0]['targets']),{6,7})

    def test_character_subfolders_produce_two_complete_candidates(self):
        report=self.analyze('boss',['robot/move/frames.png','robot/attack/frames.png','knight/move/frames.png','knight/attack/frames.png'])
        self.assertEqual(report['total'],2)

    def test_incomplete_multiple_characters_are_not_mixed(self):
        report=self.analyze('boss',['robot-move.png','robot-attack.png','knight-move.png'])
        self.assertFalse(report['canGenerate'])
        self.assertIn('动作不齐全',report['issues'][0])

    def test_same_action_multiple_targets_is_explicit(self):
        self.scan['items'].append(target(9,'other-move.png',['小怪']))
        report=self.analyze('enemy',['robot-move.png'])
        self.assertFalse(report['canGenerate'])
        self.assertIn('无法自动确定',report['issues'][0])

    def test_empty_folders_preserve_original(self):
        report=analyze_folders(self.scan,{},lambda _:[])
        self.assertFalse(report['canGenerate'])
        self.assertEqual(report['slots'],[])

    def test_sequence_gaps_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ['move_00.png','move_02.png']:
                (Path(temp)/name).write_bytes(b'not-an-image')
            report=analyze_folders(self.scan,{'enemy':temp},server.collect_assets)
            self.assertFalse(report['canGenerate'])
            self.assertIn('编号不连续',report['issues'][0])


if __name__=='__main__':
    unittest.main()
