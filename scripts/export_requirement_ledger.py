"""Export reviewed requirement mappings without copying private source text."""
import csv
import io
import json
import re
from pathlib import Path

from traceability import ROOT, REGISTRY, validate

# Logical boundaries, not services or delivered capabilities. Cross-cutting
# documents map to all planes; no source requirement is discarded by a filter.
SECTION_PLANES = {
    0: 'I;II;III;IV', 1: 'I', 2: 'II;IV', 3: 'III;IV', 4: 'II;III',
    5: 'I;II;III;IV', 6: 'II;III;IV', 7: 'I;II;III;IV', 8: 'II;III',
    9: 'I;II;III;IV', 10: 'III;IV', 11: 'I;II;III;IV', 12: 'IV',
    13: 'II;III;IV', 14: 'I;II;IV', 15: 'III;IV', 16: 'III;IV',
    17: 'II;IV', 18: 'III;IV',
}


def export(registry):
    errors = validate(registry)
    if errors:
        raise ValueError('Traceability validation failed: ' + '; '.join(errors))
    stream = io.StringIO(newline='')
    names = ['requirement_id', 'macroplanes', 'source_path', 'start_line', 'end_line',
             'source_sha256', 'implementation', 'tests', 'evidence',
             'implementation_status', 'acceptance_status', 'dependencies',
             'acceptance_test', 'source_gap']
    writer = csv.DictWriter(stream, names, lineterminator='\n')
    writer.writeheader()
    for row in registry['requirements']:
        rid = row['requirement_id']
        match = re.fullmatch(r'S(\d{2})', rid) or re.match(r'(?:CLAUSE|ARCHIVED|HISTORICAL)-(\d+)-', rid)
        planes = SECTION_PLANES[int(match[1])] if match else 'I;II;III;IV'
        source = row['source_anchor']
        writer.writerow({'requirement_id': rid, 'macroplanes': planes,
                         'source_path': source['path'], 'start_line': source['start_line'],
                         'end_line': source['end_line'], 'source_sha256': source['source_sha256'],
                         **{out: ';'.join(x['path'] for x in row[key]) for out, key in
                            [('implementation', 'implementation'), ('tests', 'test'), ('evidence', 'evidence')]},
                         **{key: row[key] for key in ['implementation_status', 'acceptance_status', 'acceptance_test']},
                         'dependencies': ';'.join(row['dependencies']), 'source_gap': row.get('source_gap') or ''})
    return stream.getvalue()


if __name__ == '__main__':
    output = export(json.loads((ROOT/REGISTRY).read_text()))
    for name in ('REQUIREMENT_LEDGER.csv', 'TRACEABILITY.csv'):
        (ROOT/'docs/apex_status'/name).write_text(output)
    print(json.dumps({'status': 'EXPORTED_SOURCE_TRACE_NOT_ACCEPTANCE',
                      'files': ['REQUIREMENT_LEDGER.csv', 'TRACEABILITY.csv']}))
