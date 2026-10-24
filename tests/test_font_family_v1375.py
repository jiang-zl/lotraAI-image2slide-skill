"""Coarse family decisions, finite resources, sticky adoption and fine evidence."""
import copy
import importlib
from pathlib import Path
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import font_family as family, font_collection as collection, font_resources as resources
from core import font_contract as fonts, font_selection as selection
from core.common import digest, read_json


class VisualFamily(unittest.TestCase):
    def setUp(self):
        self.helper = importlib.import_module('test_font_steps_v1374').FontSteps()
        self.helper.setUp(); self.addCleanup(self.helper.doCleanups)
        self.helper.state['font_family_policy'] = family.POLICY
        self.first = self.helper.fixture.face('Microsoft YaHei')
        self.second = self.helper.fixture.face('华文雅黑')
        self.faces = {face['id']: {**face, 'language': 'zh', 'style_class': 'sans'} for face in (self.first, self.second)}
        stack = ExitStack(); self.addCleanup(stack.close)
        stack.enter_context(patch.object(resources, 'available', return_value=list(self.faces.values())))
        stack.enter_context(patch.object(collection, 'prepare', return_value={'faces': self.faces, 'revision': 'family-fixture'}))
        stack.enter_context(patch.object(collection, 'load', return_value={'faces': self.faces, 'revision': 'family-fixture'}))

    def test_chinese_names_and_explicit_finite_yahei_group(self):
        request = {'role': 'ea'}
        self.assertEqual(family.display_name(self.first, 'zh'), '微软雅黑')
        self.assertEqual(family.family_key(self.helper.state, request, self.first), '雅黑')
        self.assertEqual(family.family_key(self.helper.state, request, self.second), '雅黑')
        third = {'family': 'Other Sans', 'aliases': ['华文黑体']}
        self.assertNotEqual(family.family_key(self.helper.state, request, third), '雅黑')

    def test_one_visual_family_skips_unnecessary_vendor_choice(self):
        self.helper.prepare_samples(); packet = self.helper.packet()
        self.assertEqual(packet['required_step'], 'bind')
        self.assertEqual(packet['family_gate']['policy'], family.POLICY)
        for candidates in packet['display_candidates'].values():
            self.assertEqual({face['visual_family'] for face in candidates}, {'雅黑'})

    def bind(self):
        self.helper.prepare_samples(); packet = self.helper.packet(); values = []
        for request in packet['requests']:
            ref = packet['source_glyph_rankings'][request['id']]
            ranking = read_json(self.helper.task/ref['path']); face = self.faces[ranking['selected_resource']]
            values.append({'request_id': request['id'], 'family': face['family'], 'resource_id': face['id'],
                'origin': 'raster_inference', 'status': 'approximate', 'comparison_ref': ref,
                'alternatives': [other['family'] for other in self.faces.values() if other['id'] != face['id']],
                'evidence': {'source_hash': self.helper.state['source']['sha256'], 'roi': request['roi'],
                             'description': 'Original source supports the visual Yahei family'}})
        self.helper.receive(packet, 'font_bindings', values)
        return packet

    def test_first_real_binding_records_coarse_family_and_stays_staged(self):
        self.bind()
        self.assertNotIn('font_contract', self.helper.state)
        self.assertEqual({row['family'] for row in self.helper.state['font_groups'].values()}, {'雅黑'})
        pending = self.helper.state['font_pending_candidate']['staged_font_contract']
        self.assertEqual({row['visual_family'] for row in pending['bindings'].values()}, {'雅黑'})

    def test_deferred_numeric_ranking_keeps_adopted_physical_face(self):
        self.bind(); state = self.helper.state
        state['font_contract'] = copy.deepcopy(state['font_pending_candidate']['staged_font_contract'])
        request = fonts.requests(self.helper.scene, state)[0]
        prior = state['font_contract']['bindings'][request['id']]
        other = next(face for face in self.faces.values() if face['id'] != prior['resource']['id'])
        state['font_contract']['bindings'][request['id']] = {**prior, 'family': other['family'], 'resource': other}
        ref = collection.ranking(self.helper.task, state, request, extend=True)
        self.assertEqual(read_json(self.helper.task/ref['path'])['selected_resource'], other['id'])

    def test_probability_or_one_diagnostic_glyph_cannot_refine(self):
        self.bind(); request = fonts.requests(self.helper.scene, self.helper.state)[0]
        current = {'family': '雅黑'}; ranking = {'extended': True, 'samples': {'samples': [{'character': '中', 'roi': [0, 0, 16, 25]}]}}
        value = {'fine_family': self.first['family'], 'comparison_ref': {'path': 'current', 'sha256': 'a'*64}}
        proof = {'family_refinement': {'confidence': 'high', 'reason': 'A declared high probability',
                 'family': self.first['family'], 'comparison_ref': value['comparison_ref'], 'features': []}}
        with self.assertRaisesRegex(ValueError, 'two distinct'):
            family.refinement(self.helper.state, request, value, current, ranking, list(self.faces.values()), proof)

    def test_legacy_tasks_keep_exact_family_decisions(self):
        request = {'role': 'ea'}
        self.assertEqual(family.family_key({}, request, self.first), self.first['family'])


if __name__ == '__main__':
    unittest.main()
