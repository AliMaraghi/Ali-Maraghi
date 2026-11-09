"""Review prioritization using evidence gates and explicit scenario intervals."""
from decimal import Decimal
from apex.domains import evaluate_opportunity
from .engine import evaluate


def rank_opportunities(candidates, workspace, now=None):
    if not isinstance(candidates, (list, tuple)) or len(candidates) > 100:
        raise ValueError('At most 100 candidate pairs are supported')
    rows, ids = [], set()
    for case, scenario in candidates:
        if case.domain != 'opportunity' or scenario.opportunity_id != case.id or case.id in ids:
            raise ValueError('Unique matching opportunity case/scenario IDs required')
        ids.add(case.id)
        review = evaluate(case, workspace, now)
        economics = evaluate_opportunity(scenario)
        reasons = sorted({x['code'] for x in review['critic']['findings']})
        if Decimal(economics['cash_at_risk_gbp']) > 0:
            reasons.append('FUNDING_NOT_AUTHORIZED')
        if Decimal(economics['expected_net_value_gbp']['low']) < 0:
            reasons.append('NEGATIVE_DOWNSIDE_SCENARIO')
        rows.append({'id': case.id, 'review_status': 'BLOCKED' if reasons else 'REVIEWABLE_NOT_VALIDATED',
                     'blockers': reasons, 'economics': economics, 'evidence_review': review})
    rows.sort(key=lambda r: (bool(r['blockers']),
                            -Decimal(r['economics']['expected_net_value_gbp']['low']),
                            r['economics']['time_to_first_action_minutes'], r['id']))
    return {'ranking': rows, 'method': 'Reviewable first, then assumed lower net value descending, time ascending, ID',
            'uncertainty': 'Intervals are operator assumptions; ordering is not calibrated capture probability.',
            'verified_demand': False, 'actions_executed': []}
