"""Evidence-linked, rule-based candidate proposals; no claim of autonomous insight."""
from .engine import evaluate


def propose(case, workspace, now=None):
    review = evaluate(case, workspace, now)
    checks = {x['id']: x for x in review['evidence_checks']}
    sources = {x.id: x for x in case.evidence}
    proposals, excluded = [], []
    for claim in case.claims:
        refs = [ref for ref in claim.evidence_ids if ref in sources
                and sources[ref].claim_id == claim.id
                and not checks[ref]['issues']]
        if claim.kind != 'observation' or not refs:
            excluded.append(claim.id)
            continue
        support = [ref for ref in refs if sources[ref].stance == 'supports']
        contrary = [ref for ref in refs if sources[ref].stance == 'refutes']
        if not support:
            excluded.append(claim.id)
            continue
        # Bounded causal families, each has a distinct intervention/measurement.
        families = [
            ('process', 'A repeatable process constraint produces the reported observation',
             'Changing the constrained step changes the measured outcome',
             'A controlled change leaves the outcome unchanged'),
            ('measurement', 'Selection or measurement bias produces the apparent pattern',
             'Independent sampling weakens or reverses the observed pattern',
             'The pattern persists under independent representative sampling'),
            ('context', 'A neglected contextual variable explains the outcome',
             'Stratifying by context explains variation better than the proposed intervention',
             'Context stratification adds no explanatory value'),
        ]
        for family, mechanism, prediction, falsifier in families:
            proposals.append({'id': f'{claim.id}-{family}', 'claim_id': claim.id,
                              'observation': claim.statement, 'mechanism': mechanism,
                              'prediction': prediction, 'falsifier': falsifier,
                              'evidence_refs': support, 'contrary_refs': contrary,
                              'status': 'UNTESTED_RULE_BASED_HYPOTHESIS'})
        if len(proposals) >= 9:
            break
    return {'case_id': case.id, 'domain': case.domain,
            'status': 'PROPOSALS_FOR_REVIEW' if proposals else 'BLOCKED_NO_ELIGIBLE_OBSERVATIONS',
            'hypotheses': proposals, 'excluded_claims': excluded,
            'negative_space': [{'claim_id': c.id, 'question': 'Which affected group or missing measurement would distinguish competing explanations?',
                                'second_order_test': 'Measure correction effort and displaced work as well as the headline outcome'}
                               for c in case.claims[:3]],
            'baseline': case.baseline, 'source_review': review,
            'limits': 'Source integrity is not truth. Causal families are templates, not discoveries or proof of novelty.',
            'actions_executed': [], 'empirical_superiority_proven': False}
