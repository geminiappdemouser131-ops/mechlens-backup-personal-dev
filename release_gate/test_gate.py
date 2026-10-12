"""Small offline gate tests, deliberately outside the project's tests/ tree."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import gate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project = Path(__file__).resolve().parents[1]
        for path in gate.PATHS + ['release_gate/repository_context.json']:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / path, dest)

    def write(self, path, data):
        (self.root / path).write_text(json.dumps(data), encoding='utf-8')

    def candidate(self, value=3.9e-5, release='2.17.0'):
        doc = json.loads((self.root / gate.PATHS[0]).read_text())
        doc['release'] = release
        for row in doc['results']:
            row.pop('note', None)
        doc['results'][-1]['max_logit_delta'] = value
        longer = copy.deepcopy(doc['results'][-1])
        longer.update(case='longer_prompt')
        doc['results'].append(longer)
        doc['summary'] = {'total': 7, 'passed': 7, 'failed': 0}
        doc['gemma3_intermediate_check'] = {'max_absolute_delta': 1e-6, 'tolerance': 1e-5}
        self.write(f'Configs/acceptance_test_output_v{release}.json', doc)
        return doc

    def ready(self):
        self.candidate()
        config = self.root / gate.PATHS[1]
        config.write_text(config.read_text() + '\nci_confirmation: { release: "2.17.0", status: green, confirmed_by: maintainer, evidence: "recorded CI run" }\n')
        sweep = self.root / gate.PATHS[8]
        sweep.write_text(sweep.read_text() + '2.17.0,2026-07-29,green,14,14,0,local,candidate sweep\n')

    def states(self, report):
        return {g['id']: g['result'] for g in report['gates']}

    def test_config_target_and_historical_sweeps(self):
        report = gate.audit(self.root)
        self.assertEqual(report['release'], '2.17.0')
        self.assertEqual(self.states(report)['demo_sweep'], 'PENDING')
        self.assertTrue(all(not r['counts_toward_readiness'] for r in report['historical_evidence']))
        p = self.root / gate.PATHS[1]
        p.write_text(p.read_text().replace('2.17.0', '2.18.0'))
        self.assertEqual(gate.audit(self.root)['release'], '2.18.0')

    def test_threshold_boundaries(self):
        for value, expected in [(9.99e-5, 'PASS'), (1e-4, 'PASS'), (1.00001e-4, 'FAIL')]:
            with self.subTest(value=value):
                self.candidate(value)
                self.assertEqual(self.states(gate.audit(self.root))['numerical_acceptance'], expected)

    def test_original_summary_contradiction_retained_but_historical(self):
        report = gate.audit(self.root)
        self.assertEqual(report['contradictions'][0]['scope'], 'historical')
        self.assertEqual(report['contradictions'][0]['result'], 'FAIL')
        self.assertEqual(len(report['contradictions'][0]['evidence']), 2)
        self.assertNotIn('FAIL', self.states(report).values())
        config = self.root / gate.PATHS[1]
        config.write_text(config.read_text().replace('next: { version: "2.17.0"', 'next: { version: "2.16.0"'))
        self.assertEqual(self.states(gate.audit(self.root))['evidence_consistency'], 'FAIL')

    def test_candidate_false_pass_flags(self):
        self.candidate(1.3e-4)
        report = gate.audit(self.root)
        self.assertEqual(self.states(report)['evidence_consistency'], 'FAIL')
        self.assertTrue(any(c['scope'] == 'candidate' for c in report['contradictions']))
        self.assertEqual(gate.exit_code(report), 1)

    def test_missing_unreadable_and_wrong_release_pending(self):
        self.assertEqual(gate.exit_code(gate.audit(self.root)), 2)
        path = 'Configs/acceptance_test_output_v2.17.0.json'
        (self.root / path).write_text('{broken')
        self.assertEqual(self.states(gate.audit(self.root))['numerical_acceptance'], 'PENDING')
        doc = self.candidate()
        doc['release'] = '2.15.0'
        self.write(path, doc)
        self.assertEqual(self.states(gate.audit(self.root))['numerical_acceptance'], 'PENDING')
        (self.root / gate.PATHS[5]).unlink()
        self.assertEqual(self.states(gate.audit(self.root))['evidence_inventory'], 'PENDING')

    def test_ci_requires_explicit_matching_confirmation(self):
        self.assertEqual(self.states(gate.audit(self.root))['ci_confirmation'], 'PENDING')
        config = self.root / gate.PATHS[1]
        config.write_text(config.read_text() + '\nci_confirmation:\n  release: "2.16.0"\n  status: green\n  confirmed_by: maintainer\n  evidence: run-record\n')
        self.assertEqual(self.states(gate.audit(self.root))['ci_confirmation'], 'PENDING')
        config.write_text(config.read_text().replace('release: "2.16.0"', 'release: "2.17.0"'))
        self.assertEqual(self.states(gate.audit(self.root))['ci_confirmation'], 'PASS')

    def test_ready_and_nonblocking_issue(self):
        self.ready()
        report = gate.audit(self.root)
        self.assertEqual(report['decision'], 'READY')
        self.assertEqual(gate.exit_code(report), 0)
        self.assertEqual(report['advisories'][0]['issue'], 1108)
        self.assertFalse(report['advisories'][0]['blocking'])
        self.assertEqual(report['advisories'][0]['status'], 'in-progress')

    def test_missing_regression_measurement_pending(self):
        doc = self.candidate()
        del doc['gemma3_intermediate_check']
        self.write('Configs/acceptance_test_output_v2.17.0.json', doc)
        self.assertEqual(self.states(gate.audit(self.root))['gemma3_regression'], 'PENDING')

    def test_read_only_provenance_and_standalone_dashboard(self):
        before = {p: (self.root / p).read_bytes() for p in gate.PATHS}
        report = gate.audit(self.root)
        rendered = gate.dashboard(report)
        self.assertEqual(len(report['provenance']), 11)
        self.assertEqual({p['path'] for p in report['provenance']}, set(gate.PATHS))
        self.assertIn('NOT_READY', rendered)
        self.assertIn('pending gates', rendered)
        self.assertNotIn('<script src=', rendered)
        self.assertNotIn('<link ', rendered)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in gate.PATHS})
        report['advisories'][0]['title'] = '<script>unsafe</script>'
        self.assertNotIn('<script>unsafe</script>', gate.dashboard(report))

    def test_nonfinite_and_bad_schema(self):
        for value in [float('nan'), float('inf'), -1]:
            self.candidate(value)
            report = gate.audit(self.root)
            self.assertEqual(self.states(report)['numerical_acceptance'], 'FAIL')
            json.dumps(report, allow_nan=False)
        self.write('Configs/acceptance_test_output_v2.17.0.json', {'release': '2.17.0', 'results': None})
        self.assertEqual(self.states(gate.audit(self.root))['numerical_acceptance'], 'PENDING')


if __name__ == '__main__':
    unittest.main()
