"""Independent source rendering, physical scale, ambiguity and native unit guards."""
import copy
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'skills/lotra-image2slide-skill/scripts'))
from core import source_font_size as sizes, typography_units as units
from core import typography_measurement as measurement, capture_target
from core.common import digest, identity, read_json, write_json
from core.source_typography import _size_groups
from core import source_typography, font_contract
from core.font_resources import describe


class Typography(unittest.TestCase):
    def setUp(self):
        self.fixture = importlib.import_module('test_font_workflow_v1373').Fonts()
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.task = self.fixture.task
        # The older fixture's identical narrow triangles have deliberately
        # degenerate advance rounding. Use explicit em-wide advances for tests
        # that require a uniquely distinguishable multi-character source.
        path = self.fixture.root/'Size-metrics.ttf'
        font = TTFont(self.fixture.old['path'])
        font['hmtx'].metrics = {key: (1000, value[1]) for key, value in font['hmtx'].metrics.items()}
        font.save(path); font.close(); self.face = describe(path)

    def source(self, expected=18, text='ABab0123ABab', scale=.75):
        image = Image.new('RGB', (640, 130), 'white'); draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(self.face['path'], size=expected/scale)
        box = draw.textbbox((20, 20), text, font=font)
        draw.text((20, 20), text, font=font, fill='black')
        sample = {'text': text, 'roi': [box[0]-5, box[1]-5, box[2]-box[0]+10, box[3]-box[1]+10]}
        return image, sample

    def scene(self):
        return {'typography_policy': units.POLICY, 'typography_units': {'font_size': 'pt'},
                'canvas': {'unit': 'px', 'width': 640, 'height': 130, 'target_width_inches': 640/96},
                'objects': [{'id': 'label', 'render_type': 'text', 'style': {'font_size': 12.33},
                             'content': {'runs': [{'text': 'AB', 'font_scale': .8}]}}]}

    def test_known_half_point_sizes_from_independent_text_draw(self):
        for expected in (12, 24):
            with self.subTest(size=expected):
                image, sample = self.source(expected)
                result = sizes.fit(image, [sample], self.face, .75)
                self.assertEqual(result['recommended_pt'], expected)
                self.assertEqual(result['status'], 'IDENTIFIED')
                self.assertLessEqual(result['candidate_count'], 17)

    def test_fractional_size_is_retained_when_pixels_cannot_distinguish_it(self):
        image, sample = self.source(17.5)
        result = sizes.fit(image, [sample], self.face, .75)
        self.assertIn(17.5, result['plausible_sizes_pt'], str(result['candidates'][:2]))
        if len(result['plausible_sizes_pt']) > 1:
            self.assertEqual(result['status'], 'AMBIGUOUS')
            self.assertIsNone(result['recommended_pt'])

    def test_output_physical_scale_changes_points_not_source_ink(self):
        image, sample = self.source(18)
        first = sizes.fit(image, [sample], self.face, .75)
        second = sizes.fit(image, [sample], self.face, 1.5)
        self.assertIn(18, first['plausible_sizes_pt'], str(first['candidates'][:2]))
        self.assertIn(36, second['plausible_sizes_pt'], str(second['candidates'][:2]))
        self.assertAlmostEqual(second['points_per_source_pixel']/first['points_per_source_pixel'], 2)

    def test_multiple_sizes_remain_explicitly_ambiguous(self):
        image, sample = self.source(12, 'A')
        result = sizes.fit(image, [sample], self.face, .75, 2)
        self.assertGreater(len(result['plausible_sizes_pt']), 1)
        self.assertEqual(result['status'], 'AMBIGUOUS')
        self.assertIsNone(result['recommended_pt'])

    def test_disagreeing_samples_cannot_be_averaged_into_a_size(self):
        image, sample = self.source(12)
        other, second = self.source(24)
        image.paste(other, (0, 65))
        second['roi'][1] += 65
        # Extend the independent source rather than clip the second sample.
        extended = Image.new('RGB', (640, 260), 'white')
        original, first = self.source(12)
        extended.paste(original); extended.paste(other, (0, 130)); second['roi'][1] += 65
        result = sizes.fit(extended, [first, second], self.face, .75)
        self.assertEqual(result['status'], 'NO_SUPPORTED_SIZE')
        self.assertIsNone(result['recommended_pt'])

    def test_ocr_normalized_coordinates_are_rejected(self):
        image, sample = self.source(); sample['domain'] = 'ocr_normalized'
        with self.assertRaisesRegex(ValueError, 'SAMPLE_DOMAIN_REQUIRED'):
            sizes.fit(image, [sample], self.face, .75)

    def test_changed_font_resource_is_rejected(self):
        image, sample = self.source(); face = {**self.face, 'file_sha256': identity('different bytes')}
        with self.assertRaisesRegex(ValueError, 'FONT_CHANGED'):
            sizes.fit(image, [sample], face, .75)

    def test_half_point_conversion_is_decimal_and_repeat_safe(self):
        for raw, expected in [('12.24', 12), ('12.25', 12.5), ('12.33', 12.5), ('12.75', 13), ('0.33', .5)]:
            self.assertEqual(units.half_point(raw), expected)
        scene = self.scene(); result = units.canonicalize(scene)
        self.assertEqual(result['objects'][0]['style']['font_size'], 12.5)
        self.assertEqual(result['objects'][0]['content']['runs'][0]['font_size'], 10)
        self.assertEqual(units.canonicalize(result), result)
        self.assertEqual(scene['objects'][0]['style']['font_size'], 12.33)

    def test_missing_or_unknown_units_are_not_silently_points(self):
        for declaration in ({}, {'font_size': 'px'}):
            scene = self.scene(); scene['typography_units'] = declaration
            with self.assertRaisesRegex(ValueError, 'UNIT_REQUIRED'):
                units.canonicalize(scene)

    def test_shape_only_scene_has_no_spurious_font_unit_or_plane_requirement(self):
        scene = self.scene(); scene.pop('typography_units')
        scene['objects'] = [{'id': 'box', 'render_type': 'shape', 'style': {}, 'content': {'preset': 'rect'}}]
        self.assertEqual(units.canonicalize(scene), scene)
        units.validate(scene)
        self.assertEqual(source_typography.require(self.task, {'typography_policy': units.POLICY}, scene, {}), scene)

    def test_cached_ocr_only_proposes_original_domain_samples(self):
        state, scene = self.context('fronto_parallel')
        folder = self.task/'source/ocr'; folder.mkdir()
        anchors = folder/'anchors.json'
        write_json(anchors, {'status': 'SOURCE_OCR_CANDIDATE_ANCHORS', 'source_hash': state['source']['sha256'],
            'lines': [{'text': 'ABab', 'roi': [20, 20, 100, 30],
                       'words': [{'text': 'ABab', 'roi': [20, 20, 100, 30]}]}]})
        descriptor = {'status': 'SOURCE_OCR_CANDIDATE_ANCHORS', 'source_hash': state['source']['sha256'],
                      'path': 'source/ocr/anchors.json', 'sha256': digest(anchors)}
        write_json(self.task/'source/ocr-descriptor.json', descriptor)
        request = {'roi': [10, 10, 300, 80], 'characters': 'ABab'}
        result = measurement.propose_samples(self.task, state, request, 'ABab')
        self.assertEqual(len(result), 1); self.assertEqual(result[0]['domain'], 'task_source')
        self.assertIn('CONFIRMATION_REQUIRED', result[0]['status'])
        self.assertEqual(measurement.propose_samples(self.task, state, request, 'Other text'), [])
        anchors.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'OCR_CHANGED'):
            measurement.propose_samples(self.task, state, request, 'ABab')

    def context(self, basis=None, text='ABab0123ABab'):
        image, _ = self.source(12, text); original = self.task/'source/original.png'; image.save(original)
        state = {'source': {'path': 'source/original.png', 'sha256': digest(original)}, 'source_size': [640, 130]}
        scene = self.scene()
        if basis:
            proof = self.task/'source/measurement.json'
            write_json(proof, {'source_hash': state['source']['sha256'], 'observer': 'human',
                               'observations': 'Independent known flat source fixture', 'measurement_kind': basis})
            scene['typography_measurement'] = {'kind': basis, 'source_uncertainty_px': .5,
                'evidence': {'path': 'source/measurement.json', 'sha256': digest(proof)}}
        return state, scene

    def test_crop_or_full_image_alone_does_not_establish_measurement_plane(self):
        state, scene = self.context()
        with self.assertRaisesRegex(ValueError, 'MEASUREMENT_BASIS_REQUIRED'):
            measurement.context(self.task, state, scene, copy.deepcopy(scene))

    def test_bound_flat_source_uses_declared_physical_scale(self):
        state, scene = self.context('fronto_parallel')
        result = measurement.context(self.task, state, scene, copy.deepcopy(scene))
        self.assertEqual(result['points_per_source_pixel'], .75)
        self.assertFalse(result['historical_original_pt_identified'])
        changed = copy.deepcopy(scene); changed['typography_measurement']['kind'] = 'projected_appearance'
        with self.assertRaisesRegex(ValueError, 'MEASUREMENT_REBIND_REQUIRED'):
            measurement.context(self.task, state, changed, scene)

    def test_source_group_intersects_evidence_without_widening_failure(self):
        def row(values):
            return {'size_group': 'labels', 'model': {'plausible_sizes_pt': values, 'recommended_pt': None}}
        rows = {'a': row([12, 12.5]), 'b': row([12.5, 13])}; errors = []
        groups = _size_groups(rows, errors, {'kind': 'fronto_parallel'})
        self.assertEqual(errors, []); self.assertEqual(groups[0]['plausible_sizes_pt'], [12.5])
        self.assertEqual(rows['a']['model']['recommended_pt'], 12.5)
        rows['a']['model']['plausible_sizes_pt'] = []
        errors = []; _size_groups(rows, errors, {'kind': 'fronto_parallel'})
        self.assertIn('SIZE_GROUP_CONFLICT', errors[0]['reason'])

    def test_projected_local_sizes_cannot_claim_rectified_group_equality(self):
        rows = {'a': {'size_group': 'labels', 'model': {'plausible_sizes_pt': [12]}}}; errors = []
        _size_groups(rows, errors, {'kind': 'projected_appearance'})
        self.assertIn('SIZE_GROUP_PLANE_REQUIRED', errors[0]['reason'])

    def preflight(self, declared=12, text='ABab0123ABab'):
        state, scene = self.context('fronto_parallel', text=text)
        image, sample = self.source(12, text); image.save(self.task/state['source']['path'])
        scene['source'] = state['source']
        obj = scene['objects'][0]
        obj['semantic_type'] = 'label'
        obj['bbox'] = [10, 10, 610, 110]
        obj['style'] = {'font': self.face['family'], 'font_size': declared, 'color': '000000'}
        obj['content'] = {'runs': [{'text': sample['text']}]}
        obj['typography_samples'] = {'p0.r0': {'source_hash': state['source']['sha256'],
            'observer': 'human', 'source_evidence': scene['typography_measurement']['evidence'], 'samples': [sample]}}
        requests = font_contract.requests(scene, state)
        scene['font_plan'] = {'bindings': {request['id']: {'resource': self.face} for request in requests}}
        file = self.task/'source/frozen-scene.json'; write_json(file, scene)
        state['typography_policy'] = units.POLICY
        contract = {'source_scene': {'path': 'source/frozen-scene.json', 'sha256': digest(file)}}
        return state, scene, contract

    def test_preflight_checks_actual_source_size_before_any_native_write(self):
        state, scene, contract = self.preflight()
        result = source_typography.require(self.task, state, scene, contract)
        self.assertEqual(result['objects'][0]['style']['font_size'], 12)
        records = list((self.task/'source').glob('Typography-preflight-*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(read_json(records[0])['status'], 'PRE_RENDER_SIZE_SCREENED')
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_oversized_declaration_is_blocked_before_native_write(self):
        state, scene, contract = self.preflight(24)
        with self.assertRaisesRegex(ValueError, 'SIZE_MISMATCH'):
            source_typography.require(self.task, state, scene, contract)
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_supported_ambiguous_construction_retains_uncertainty_and_exact_bounds(self):
        state, scene, contract = self.preflight(text='A')
        scene['typography_measurement']['source_uncertainty_px'] = 2
        frozen = self.task/contract['source_scene']['path']; write_json(frozen, scene)
        contract['source_scene']['sha256'] = digest(frozen)
        source_typography.require(self.task, state, scene, contract)
        record = read_json(next((self.task/'source').glob('Typography-preflight-*.json')))
        row = next(iter(record['rows'].values()))
        self.assertEqual(row['model']['status'], 'AMBIGUOUS')
        self.assertIsNone(row['model']['recommended_pt'])
        self.assertIn(12, row['construction_size_decision']['supported_sizes_pt'])
        self.assertFalse(row['construction_size_decision']['historical_original_pt_identified'])
        self.assertEqual(row['construction_size_decision']['status'], 'SUPPORTED_ESTIMATE')
        self.assertEqual(row['model']['measurement_error_budget']['boundary_px'], 2.5)
        self.assertFalse(record['actual_render_acceptance'])
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_unsupported_size_still_blocked_when_model_is_ambiguous(self):
        state, scene, contract = self.preflight(24, text='A')
        scene['typography_measurement']['source_uncertainty_px'] = 2
        frozen = self.task/contract['source_scene']['path']; write_json(frozen, scene)
        contract['source_scene']['sha256'] = digest(frozen)
        with self.assertRaises(source_typography.PreflightRequired) as caught:
            source_typography.require(self.task, state, scene, contract)
        row = next(iter(caught.exception.record['rows'].values()))
        self.assertEqual(row['model']['status'], 'AMBIGUOUS')
        self.assertNotIn(24, row['construction_size_decision']['supported_sizes_pt'])
        self.assertEqual(row['construction_size_decision']['status'], 'DECISION_REQUIRED')
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_shared_size_choice_cannot_keep_different_group_sizes(self):
        rows = {'a': {'size_group': 'labels', 'font_size_pt': 12,
                      'model': {'plausible_sizes_pt': [12, 12.5], 'recommended_pt': None}},
                'b': {'size_group': 'labels', 'font_size_pt': 12.5,
                      'model': {'plausible_sizes_pt': [12, 12.5], 'recommended_pt': None}}}
        errors = []; _size_groups(rows, errors, {'kind': 'rectified_plane'})
        choices = {source_typography._construction_choice([row['model']], row['font_size_pt']) for row in rows.values()}
        self.assertEqual(choices, {12})
        rows['b']['model']['plausible_sizes_pt'] = [13]
        # A fresh fit does not carry another fit's group intersection.
        for row in rows.values():
            row['model'].pop('group_plausible_sizes_pt', None); row['model'].pop('group_selected_pt', None)
        self.assertIsNone(source_typography._construction_choice([row['model'] for row in rows.values()], 12))

    def recovery_case(self):
        state, scene, contract = self.preflight(24)
        state['font_pending_candidate'] = {'scene': contract['source_scene'], 'baseline': None, 'allowed': None}
        with self.assertRaises(source_typography.PreflightRequired) as caught:
            source_typography.require(self.task, state, scene, contract)
        details = source_typography.recovery(self.task, state, scene, caught.exception)
        details['packet_id'] = 'size-recovery'
        return state, scene, contract, details

    def test_pre_native_recovery_accepts_phrase_and_adopts_actual_unique_fit(self):
        state, scene, contract, packet = self.recovery_case()
        before = digest(self.task/contract['source_scene']['path'])
        _, sample = self.source(12)
        result = {'packet_id': packet['packet_id'], 'typography_changes': [{
            'request_id': packet['requests'][0]['id'], 'samples': [sample],
            'source_evidence': 'Observed complete continuous phrase and its blank margins in the original.'}]}
        from core import component_workflow
        with patch.object(component_workflow, '_load', return_value=(contract, {})), \
                patch.object(font_contract, 'bind_scene', side_effect=lambda task, state, value: copy.deepcopy(value)):
            receipt = source_typography.receive_recovery(self.task, state, packet, result)
        fixed = read_json(self.task/state['font_pending_candidate']['scene']['path'])
        self.assertEqual(receipt['adopted_sizes'][0]['font_size_pt'], 12)
        self.assertEqual(source_typography.require(self.task, state, fixed, contract)['objects'][0]['content']['runs'][0]['font_size'], 12)
        self.assertEqual(digest(self.task/contract['source_scene']['path']), before)
        self.assertEqual(scene['objects'][0]['style']['font_size'], 24)
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_recovery_rejects_foreign_samples_and_direct_native_edits_atomically(self):
        state, scene, contract, packet = self.recovery_case()
        _, sample = self.source(12)
        good = {'request_id': packet['requests'][0]['id'], 'samples': [sample], 'source_evidence': 'Original phrase.'}
        for change in ({**good, 'font_size': 12}, {**good, 'request_id': 'foreign'},
                       {**good, 'samples': [{**sample, 'text': 'unrelated'}]},
                       {**good, 'samples': [{**sample, 'roi': [0, 0, 50, 30]}]},
                       {**good, 'samples': [{**sample, 'domain': 'ocr_normalized'}]}):
            with self.subTest(change=change):
                prior = identity(state)
                with self.assertRaises(ValueError):
                    source_typography.receive_recovery(self.task, state, packet, {
                        'packet_id': packet['packet_id'], 'typography_changes': [change]})
                self.assertEqual(identity(state), prior)
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_exhausted_sampling_does_not_reset_its_attempt_budget(self):
        state, scene, contract, packet = self.recovery_case()
        key = packet['requests'][0]['id']
        state['font_pending_candidate']['typography_recovery_history'] = [{'requests': [key]} for _ in range(3)]
        with self.assertRaises(source_typography.PreflightRequired) as caught:
            source_typography.require(self.task, state, scene, contract)
        packet = source_typography.recovery(self.task, state, scene, caught.exception)
        self.assertEqual(packet['requests'][0]['attempts'], 3)
        _, sample = self.source(12)
        with self.assertRaisesRegex(ValueError, 'retained sample limit'):
            source_typography.receive_recovery(self.task, state, packet, {'typography_changes': [
                {'request_id': key, 'samples': [sample], 'source_evidence': 'Original phrase.'}]})

    def test_finished_font_binding_returns_size_packet_before_candidate_write(self):
        state, scene, contract, _ = self.recovery_case()
        from core import agent_runtime as runtime, component_workflow
        state['font_pending_candidate'].update(reason=None, staged_font_contract={
            'version': font_contract.VERSION, 'bindings': {}, 'history': []})
        with patch.object(runtime, '_save'), patch.object(font_contract, 'auto_bind'), \
                patch.object(font_contract, 'packet', return_value=None), \
                patch.object(font_contract, 'bind_scene', return_value=scene), \
                patch.object(component_workflow, '_load', return_value=(contract, {})), \
                patch.object(runtime, '_packet', side_effect=lambda *args, **kw: {'kind': args[2], **kw['extra']}), \
                patch.object(runtime, '_candidate') as writer:
            result = runtime._pending_font_work(self.task, state)
        self.assertEqual(result['packet']['kind'], 'typography_source')
        self.assertEqual(len(result['packet']['requests']), 1)
        self.assertFalse(result['packet']['native_write_performed'])
        writer.assert_not_called()
        self.assertFalse(list(self.task.rglob('*.pptx')))

    def test_photo_plane_rectification_preserves_known_word_size(self):
        image, sample = self.source(12)
        for index, corners in enumerate(([[10, 10], [680, 25], [650, 220], [30, 180]],
                                         [[25, 30], [680, 10], [690, 180], [10, 220]])):
            with self.subTest(pose=index):
                source_corners = [[0, 0], [640, 0], [640, 130], [0, 130]]
                mapping = capture_target.homography(corners, source_corners)
                coefficients = (mapping/mapping[2, 2]).ravel()[:8]
                photo = image.transform((720, 250), Image.Transform.PERSPECTIVE, coefficients,
                                        Image.Resampling.BICUBIC, fillcolor=(70, 70, 70))
                raw = self.task/'source'/('photo-'+str(index)+'.png'); photo.save(raw)
                authority = self.task/'source/authority.txt'
                authority.write_text('Known authored plane is 640 by 130 pixels at the fixed physical width.', encoding='utf-8')
                plan = {'schema': capture_target.POLICY, 'kind': 'slide_surface', 'raw_source_hash': digest(raw),
                    'observer': 'human', 'corners': corners, 'output_size': [640, 130],
                    'aspect_ratio_basis': 'original_metadata', 'source_uncertainty_px': 1,
                    'source_evidence': 'Known corners of the independently rendered flat fixture',
                    'authorization': {'path': 'source/authority.txt', 'sha256': digest(authority)}}
                plan = capture_target.validate(plan, photo.size, digest(raw), self.task)
                ref, size, target = capture_target.freeze(self.task, raw, plan)
                state = {'source': ref, 'source_size': size, 'reconstruction_target': target}
                scene = self.scene(); context = measurement.context(self.task, state, scene, scene)
                self.assertEqual(context['kind'], 'rectified_plane')
                with Image.open(self.task/ref['path']) as restored:
                    result = sizes.fit(restored, [sample], self.face, .75, context['source_uncertainty_px'])
                self.assertIn(12, result['plausible_sizes_pt'], str(result['candidates'][:2]))
                self.assertTrue(capture_target.verify(self.task, state)['passed'])


if __name__ == '__main__':
    unittest.main()
