"""Read recorded release evidence without importing the project or loading models."""
import argparse
import csv
import hashlib
import html
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

LIMIT = 1e-4
PATHS = [
    'Configs/acceptance_test_output_v2.16.0.json',
    'Configs/release_config.yaml',
    'Notes/triage_1121_gemma3_logits.md',
    'Notes/issue_triage_queue.csv',
    'Adapters/acceptance_test_notes.md',
    'Adapters/adapter_authoring_checklist.md',
    'Adapters/weight_conversion_checklist.csv',
    'Releases/release_checklist.md',
    'Releases/demo_sweep_results.csv',
    'Releases/pr_merge_log.csv',
    'Releases/release_notes_v2.16.1_2026-06-27.md',
]
ROLES = [
    'Historical acceptance measurements and summary', 'Release target and gate policy',
    'Longer-prompt breach and hotfix measurements', 'Issue dispositions',
    'Acceptance methodology', 'Adapter review requirements', 'Conversion requirements',
    'Release procedure and CI confirmation requirement', 'Release-scoped demo results',
    'Merge history; not execution evidence', 'Hotfix context; not candidate execution evidence',
]


def ref(path, locator):
    return {'path': path, 'locator': locator}


def number_state(value, limit=LIMIT):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 'PENDING'
    if not math.isfinite(value) or value < 0 or value > limit:
        return 'FAIL'
    return 'PASS'


def worst(states):
    return 'FAIL' if 'FAIL' in states else 'PENDING' if 'PENDING' in states else 'PASS'


def mapping(text, key):
    """Read only a named scalar mapping from the supplied restricted YAML format.

    Supports inline {key: value} and indented scalar fields. No YAML execution,
    tags, anchors, nested values, or general-purpose YAML interpretation.
    """
    match = re.search(r'^' + re.escape(key) + r':[ \t]*([^\n]*)', text, re.M)
    if not match:
        return {}
    head = match.group(1).split('#', 1)[0].strip()
    if head.startswith('{') and head.endswith('}'):
        items = head[1:-1].split(',')
    elif not head:
        tail = text[match.end():]
        items = []
        for line in tail.splitlines():
            if not line.strip():
                continue
            if not line.startswith(' '):
                break
            items.append(line)
    else:
        return {}
    result = {}
    for item in items:
        field = re.fullmatch(r'\s*([\w-]+):\s*([^\n]*)', item)
        if not field:
            return {}
        value = field[2].split('#', 1)[0].strip().strip('\"\'')
        if any(char in value for char in '{}[]&*!') or field[1] in result:
            return {}
        result[field[1]] = value
    return result


def read_source(root, path):
    p = root / path
    try:
        data = p.read_bytes()
        text = data.decode('utf-8')
        if not text.strip():
            raise ValueError('empty file')
        return text, {'path': path, 'status': 'available',
                      'sha256': hashlib.sha256(data).hexdigest()}
    except (OSError, UnicodeError, ValueError) as error:
        return '', {'path': path, 'status': 'missing_or_unreadable',
                    'reason': type(error).__name__}


def parse_json(text):
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def rows(text):
    try:
        return list(csv.DictReader(io.StringIO(text), strict=True))
    except csv.Error:
        return []


def measures(document, path):
    result = []
    entries = document.get('results', [])
    if not isinstance(entries, list):
        return []
    for i, row in enumerate(entries):
        if not isinstance(row, dict):
            continue
        value = row.get('max_logit_delta')
        result.append({'release': document.get('release'),
                       'family': row.get('family'), 'case': row.get('case', 'suite_prompt'),
                       'checkpoint': row.get('checkpoint'),
                       'value': str(value) if isinstance(value, float) and not math.isfinite(value) else value,
                       'result': number_state(value), 'reported_pass': row.get('pass'),
                       'evidence': [ref(path, f'$.results[{i}].max_logit_delta')]})
    return result


def summary_passes(document):
    summary = document.get('summary', {})
    return (isinstance(summary, dict) and isinstance(summary.get('total'), int)
            and summary['total'] > 0 and summary.get('passed') == summary['total']
            and summary.get('failed') == 0)


def audit(root):
    sources, provenance = {}, []
    for path, role in zip(PATHS, ROLES):
        sources[path], record = read_source(root, path)
        record['role'] = role
        record['public_copy_note'] = (
            'Funding/receipt reference omitted; technical methodology preserved.'
            if path == PATHS[4] else 'Project evidence copied; no private source links included.')
        provenance.append(record)
    config = sources[PATHS[1]]
    target = mapping(config, 'next').get('version')
    if not target or not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][\w.-]+)?', target):
        target = None
    gates = []

    def gate(name, state, reason, evidence):
        gates.append({'id': name, 'result': state, 'reason': reason, 'evidence': evidence})

    missing = [p['path'] for p in provenance if p['status'] != 'available']
    gate('evidence_inventory', 'PENDING' if missing else 'PASS',
         'Missing or unreadable sources: ' + ', '.join(missing) if missing else
         'All eleven specified source files are available.', [ref(p, 'whole file') for p in missing])
    gate('release_target', 'PASS' if target else 'PENDING',
         'Release read from config next.version.' if target else 'Config next.version is missing or unsupported.',
         [ref(PATHS[1], 'next.version')])
    historical = parse_json(sources[PATHS[0]])
    measurements = measures(historical, PATHS[0])
    triage = sources[PATHS[2]]
    # These anchored extractors describe the supplied incident note, not arbitrary prose.
    breach = re.search(r'logits diverged from HF by\s*~?([\d.]+e[-+]\d+)', triage, re.I)
    fixed = re.search(r'Max delta back to\s*~?([\d.]+e[-+]\d+)', triage, re.I)
    incident_release = re.search(r'after v(\d+\.\d+\.\d+)', triage)
    fixed_release = re.search(r'Cut v(\d+\.\d+\.\d+) hotfix', triage)
    for match, release_match, case, section in [
        (breach, incident_release, 'longer_prompt', 'Symptom'),
        (fixed, fixed_release, 'after_fix', 'Resolution'),
    ]:
        if match and release_match:
            value = float(match[1])
            measurements.append({'release': release_match[1], 'family': 'gemma-3',
                                 'case': case, 'value': value, 'approximate': True,
                                 'result': number_state(value),
                                 'evidence': [ref(PATHS[2], section)]})
    candidate_path = f'Configs/acceptance_test_output_v{target}.json' if target else None
    extra_sources = []
    if candidate_path in sources:
        candidate = historical
    elif candidate_path:
        text, record = read_source(root, candidate_path)
        extra_sources.append(record)
        candidate = parse_json(text)
        measurements.extend(measures(candidate, candidate_path))
    else:
        candidate = {}
    candidate_ok = bool(target and candidate.get('release') == target)
    candidate_rows = candidate.get('results', []) if candidate_ok else []
    if not isinstance(candidate_rows, list):
        candidate_rows = []
    applicable = [m for m in measurements if target and m['release'] == target]
    numerical = worst([m['result'] for m in applicable]) if applicable else 'PENDING'
    required = {m.get('family') for m in measures(historical, PATHS[0])}
    present = {r.get('family') for r in candidate_rows if isinstance(r, dict)}
    complete = bool(candidate_rows and required and required <= present
                    and candidate.get('dtype') == 'float32'
                    and all(isinstance(r, dict) for r in candidate_rows))
    if numerical != 'FAIL' and not complete:
        numerical = 'PENDING'
    gate('numerical_acceptance', numerical,
         'Maximum absolute logit error must be finite, nonnegative and <= 1e-4 for every case; '
         'candidate needs float32 results for all families in the historical suite.',
         [ref(candidate_path or PATHS[1], '$.results / $.release / $.dtype')]
         + [e for m in applicable for e in m['evidence']])
    contradictions = []
    for document, path in [(historical, PATHS[0])] + (
        [(candidate, candidate_path)] if candidate_path and candidate_path != PATHS[0] else []
    ):
        bad = [m for m in measurements if m['release'] == document.get('release') and m['result'] == 'FAIL']
        if summary_passes(document) and bad:
            contradictions.append({'release': document.get('release'), 'result': 'FAIL',
                                   'scope': 'candidate' if target == document.get('release') else 'historical',
                                   'reported_summary': document.get('summary'),
                                   'reason': 'All-pass summary conflicts with recorded numerical breach.',
                                   'evidence': [ref(path, '$.summary')] + [e for m in bad for e in m['evidence']]})
        for m in measures(document, path):
            if m['reported_pass'] is True and m['result'] == 'FAIL':
                contradictions.append({'release': m['release'], 'result': 'FAIL',
                                       'scope': 'candidate' if target == m['release'] else 'historical',
                                       'reason': 'Per-case pass flag conflicts with its measurement.',
                                       'evidence': m['evidence']})
    consistency = 'FAIL' if any(c['scope'] == 'candidate' for c in contradictions) else 'PENDING'
    if consistency != 'FAIL' and complete and summary_passes(candidate):
        consistency = 'PASS' if (candidate['summary']['total'] == len(candidate_rows)
                                 and all(r.get('pass') is True for r in candidate_rows)) else 'FAIL'
    gate('evidence_consistency', consistency,
         'Historical contradictions remain visible; only candidate contradictions fail this gate. '
         'A complete, internally consistent candidate summary is required.',
         [ref(candidate_path or PATHS[0], '$.summary / $.results')])
    long_rows = [r for r in candidate_rows if isinstance(r, dict)
                 and r.get('family') == 'gemma-3' and r.get('case') == 'longer_prompt']
    intermediate = candidate.get('gemma3_intermediate_check', {}) if candidate_ok else {}
    if not isinstance(intermediate, dict):
        intermediate = {}
    tolerance = intermediate.get('tolerance')
    intermediate_state = 'PENDING'
    if (isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool)
            and math.isfinite(tolerance) and tolerance > 0):
        intermediate_state = number_state(intermediate.get('max_absolute_delta'), tolerance)
    regression = worst([number_state(r.get('max_logit_delta')) for r in long_rows]
                       + [intermediate_state, 'PASS' if long_rows else 'PENDING'])
    gate('gemma3_regression', regression,
         'Candidate needs the longer-prompt case plus an intermediate measurement and explicit tolerance.',
         [ref(candidate_path or PATHS[0], '$.results[case=longer_prompt] / $.gemma3_intermediate_check')])
    sweeps = rows(sources[PATHS[8]])
    current_sweeps = [(i, r) for i, r in enumerate(sweeps, 2) if target and r.get('release') == target]
    sweep_states = []
    for _, row in current_sweeps:
        try:
            run, passed, failed = (int(row[k]) for k in ('notebooks_run', 'notebooks_passed', 'failures'))
            state = ('FAIL' if failed > 0 or passed < run or row['result'] in ('red', 'fail', 'failed')
                     else 'PASS' if run > 0 and passed == run and failed == 0 and row['result'] == 'green'
                     else 'PENDING')
        except (ValueError, TypeError, KeyError):
            state = 'PENDING'
        sweep_states.append(state)
    gate('demo_sweep', worst(sweep_states) if sweep_states else 'PENDING',
         'Only rows matching the configured release count. Config green is policy, not a run record.',
         [ref(PATHS[8], f'CSV line {i}') for i, _ in current_sweeps] or [ref(PATHS[8], 'no matching release row')])
    confirmation = mapping(config, 'ci_confirmation')
    ci = 'PENDING'
    if target and confirmation.get('release') == target:
        if confirmation.get('status') in ('red', 'fail', 'failed'):
            ci = 'FAIL'
        elif (confirmation.get('status') == 'green' and confirmation.get('confirmed_by')
              and confirmation.get('evidence')):
            ci = 'PASS'
    gate('ci_confirmation', ci,
         'Explicit target-release confirmation requires release, status, confirmed_by and evidence; '
         'gates.ci: green alone is insufficient.', [ref(PATHS[1], 'ci_confirmation (absent if not recorded)')])
    advisories = []
    for i, row in enumerate(rows(sources[PATHS[3]]), 2):
        if row.get('issue') == '1108':
            advisories.append({'issue': 1108, 'title': row.get('title'), 'status': row.get('status'),
                               'blocking': False, 'disposition': 'Bram explicitly designated #1108 non-blocking.',
                               'evidence': [ref(PATHS[3], f'CSV line {i}'),
                                            ref('MAINTAINER_NOTES.md', 'Non-blocking issue disposition')]})
    context_text, context_source = read_source(root, 'release_gate/repository_context.json')
    context = parse_json(context_text)
    blockers = [dict(gate=g['id'], type='failure' if g['result'] == 'FAIL' else 'missing_or_unresolved_evidence',
                     reason=g['reason'], evidence=g['evidence']) for g in gates if g['result'] != 'PASS']
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'snapshot_notice': 'Evidence snapshot, not a live status check or a model test run.',
            'release': target, 'release_source': ref(PATHS[1], 'next.version'),
            'decision': 'NOT_READY' if blockers else 'READY', 'gates': gates, 'blockers': blockers,
            'gemma3': {'metric': 'maximum absolute logit delta', 'threshold': LIMIT,
                       'measurements': [m for m in measurements if m['family'] == 'gemma-3']},
            'measurements': measurements, 'contradictions': contradictions,
            'historical_evidence': [{'release': r.get('release'), 'reported_result': r.get('result'),
                                     'notebooks_run': r.get('notebooks_run'),
                                     'counts_toward_readiness': False,
                                     'reason': 'Historical; does not count toward the configured release.',
                                     'evidence': [ref(PATHS[8], f'CSV line {i}')]} for i, r in enumerate(sweeps, 2)
                                    if r.get('release') != target],
            'advisories': advisories, 'provenance': provenance,
            'candidate_evidence': extra_sources, 'repository_context': context,
            'repository_context_source': context_source}


def exit_code(report):
    return 1 if any(g['result'] == 'FAIL' for g in report['gates']) else 2 if report['decision'] == 'NOT_READY' else 0


def dashboard(report):
    """Render all content from the same audit; no external assets or JavaScript."""
    esc = lambda x: html.escape(str(x))

    def evidence(items):
        return '<br>'.join('<code>' + esc(e['path']) + '</code> — ' + esc(e['locator']) for e in items)

    def table(headers, data):
        return '<div class="scroll"><table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>' for row in data) + '</tbody></table></div>'

    def badge(state):
        return '<strong class="badge ' + esc(state) + '">' + esc(state) + '</strong>'

    counts = {s: sum(g['result'] == s for g in report['gates']) for s in ('PASS', 'FAIL', 'PENDING')}
    body = '<header><p class="eyebrow">TRANSFORMERLENS · RELEASE EVIDENCE</p><h1>Release readiness</h1><p>Configured release: <b>' + esc(report['release']) + '</b></p>' + badge(report['decision']) + '<p>Evidence snapshot generated at: ' + esc(report['generated_at']) + '</p></header>'
    body += '<div class="cards">' + ''.join('<div><b>' + str(counts[s]) + '</b> <span>' + s.lower() + ' gates</span></div>' for s in counts) + '</div>'
    body += '<p class="notice">An old green result does not establish readiness now. Missing evidence stays PENDING. No models or project tests were run by this gate.</p>'
    body += '<h2>Candidate gates</h2>' + table(['Gate', 'State', 'Reason', 'Evidence'], [[esc(g['id']), badge(g['result']), esc(g['reason']), evidence(g['evidence'])] for g in report['gates']])
    body += '<h2>What blocks readiness</h2>'
    for category, label in [('failure', 'Demonstrated failures'), ('missing_or_unresolved_evidence', 'Pending evidence')]:
        items = [b for b in report['blockers'] if b['type'] == category]
        body += '<h3>' + label + '</h3><ul>' + (''.join('<li><b>' + esc(b['gate']) + '</b>: ' + esc(b['reason']) + '</li>' for b in items) or '<li>None.</li>') + '</ul>'
    body += '<h2>Gemma-3 measurements</h2><p>Maximum absolute logit error threshold: <b>1e-4</b> (inclusive).</p>'
    body += table(['Release', 'Case', 'Maximum absolute logit error', 'Measurement result', 'Evidence'], [[esc(m['release']), esc(m['case']), ('approximately ' if m.get('approximate') else '') + esc(m['value']), badge(m['result']), evidence(m['evidence'])] for m in report['gemma3']['measurements']])
    body += '<h2>Summary contradictions</h2>' + table(['Release', 'Scope', 'Finding', 'Evidence'], [[esc(c['release']), esc(c['scope']), esc(c['reason']) + (' Reported counts: ' + esc(json.dumps(c['reported_summary'])) if c.get('reported_summary') else ''), evidence(c['evidence'])] for c in report['contradictions']])
    body += '<h2>Historical sweeps</h2><p>Historical — does not count toward release ' + esc(report['release']) + ' readiness.</p>'
    body += table(['Release', 'Recorded sweep result', 'Notebooks run', 'Evidence'], [[esc(h['release']), esc(h['reported_result']), esc(h['notebooks_run']) + ' notebooks', evidence(h['evidence'])] for h in report['historical_evidence']])
    body += '<h2>Non-blocking issues</h2>' + table(['Issue', 'Status', 'Disposition', 'Evidence'], [[esc(a['issue']), esc(a['status']), esc(a['disposition']), evidence(a['evidence'])] for a in report['advisories']])
    body += '<h2>Provenance — eleven specified files</h2>' + table(['Folder path', 'Availability', 'Purpose', 'SHA-256 / copy note'], [[esc(p['path']), esc(p['status']), esc(p['role']), '<code>' + esc(p.get('sha256', 'unavailable')) + '</code><br>' + esc(p['public_copy_note'])] for p in report['provenance']])
    body += '<h2>Additional candidate evidence</h2><pre>' + esc(json.dumps(report['candidate_evidence'], indent=2)) + '</pre>'
    body += '<h2>Repository context</h2><pre>' + esc(json.dumps(report['repository_context'], indent=2)) + '</pre>'
    body += '<details><summary>Complete audit JSON</summary><pre>' + esc(json.dumps(report, indent=2, allow_nan=False)) + '</pre></details>'
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Release readiness audit</title><style>body{font:16px/1.55 system-ui,sans-serif;color:#172838;background:#f1f5f6;margin:0}main{max-width:1200px;margin:auto;padding:36px}header{background:#123b49;color:white;padding:32px;border-radius:16px}.eyebrow{letter-spacing:.15em;font-size:12px}h1{font-size:38px;margin:8px 0}h2{margin-top:36px}.cards{display:flex;gap:16px;margin:22px 0}.cards div{background:white;padding:18px;border-radius:10px;flex:1}.cards b{font-size:28px}.notice{border-left:4px solid #977000;padding:16px;background:#fff7de}.badge{display:inline-block;padding:4px 10px;border-radius:5px;background:#e1e8ed;color:#203648}.PASS,.READY{background:#d2efdd;color:#14552b}.FAIL{background:#ffe1dc;color:#8c2117}.PENDING,.NOT_READY{background:#fff0be;color:#684b00}table{width:100%;border-collapse:collapse;background:white;font-size:14px}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #d9e2e6}th{background:#e5edef}code{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:16px;font-size:12px}.scroll{overflow-x:auto}summary{cursor:pointer;font-weight:bold}@media(max-width:650px){main{padding:16px}.cards{flex-direction:column}h1{font-size:28px}}@media print{body{background:white}main{padding:0}header{background:white;color:black;border:1px solid #aaa}details{display:none}table{font-size:10px}tr{break-inside:avoid}}</style><main>' + body + '</main></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output_dir or root).resolve()
    report = audit(root)
    output.mkdir(parents=True, exist_ok=True)
    for name, content in [('release_readiness_audit.json', json.dumps(report, indent=2, allow_nan=False) + '\n'),
                          ('release_readiness_dashboard.html', dashboard(report))]:
        (output / name).write_text(content, encoding='utf-8')
    print(report['decision'] + ' — release ' + str(report['release']))
    for gate in report['gates']:
        print(gate['result'] + ': ' + gate['id'])
    return exit_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
